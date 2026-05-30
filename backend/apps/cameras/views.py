from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.audit.utils import log_action
from apps.common.permissions import IsOrgAdminOrReadOnly

from .models import Camera, CameraHealthCheck
from .serializers import CameraHealthCheckSerializer, CameraSerializer
from .tasks import check_camera_health


class CameraViewSet(viewsets.ModelViewSet):
    serializer_class = CameraSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["organization", "status", "is_active"]
    search_fields = ["name", "location"]

    def get_queryset(self):
        return Camera.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()

    def perform_create(self, serializer):
        cam = serializer.save()
        log_action(
            user=self.request.user,
            action="camera.create",
            request=self.request,
            organization=cam.organization,
            metadata={"camera_id": str(cam.id), "name": cam.name},
        )

    def perform_update(self, serializer):
        cam = serializer.save()
        log_action(
            user=self.request.user,
            action="camera.update",
            request=self.request,
            organization=cam.organization,
            metadata={"camera_id": str(cam.id)},
        )

    def perform_destroy(self, instance):
        org = instance.organization
        cam_id = str(instance.id)
        instance.delete()
        log_action(
            user=self.request.user,
            action="camera.delete",
            request=self.request,
            organization=org,
            metadata={"camera_id": cam_id},
        )

    @action(detail=True, methods=["post"], url_path="test-connection")
    def test_connection(self, request, pk=None):
        """Trigger an async RTSP TCP probe (Phase 1 placeholder for real RTSP handshake)."""
        cam = self.get_object()
        check_camera_health.delay(str(cam.id))
        return Response(
            {"detail": "Health check enqueued."}, status=status.HTTP_202_ACCEPTED
        )


class CameraHealthCheckViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CameraHealthCheckSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["camera", "status"]

    def get_queryset(self):
        return CameraHealthCheck.objects.filter(
            camera__organization__memberships__user=self.request.user
        ).distinct()


router = DefaultRouter()
router.register(r"health-checks", CameraHealthCheckViewSet, basename="camera-healthcheck")
router.register(r"", CameraViewSet, basename="camera")
