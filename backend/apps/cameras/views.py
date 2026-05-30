from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from apps.audit.utils import log_action
from apps.common.permissions import IsOrgAdminOrReadOnly

from .models import Camera, CameraHealthCheck, Zone
from .onvif_discovery import probe_subnet, ws_discovery
from .serializers import CameraHealthCheckSerializer, CameraSerializer, ZoneSerializer
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
        # Bootstrap analytics for a brand-new camera so the user sees real
        # numbers immediately, without having to draw zones first:
        #   * a horizontal LINE zone across the middle of the frame counts
        #     anything that crosses it (people IN/OUT, vehicles IN/OUT).
        # Existing cameras / explicit zones are left untouched.
        try:
            from .models import Zone  # local import to avoid circular at import time
            if not Zone.objects.filter(camera=cam).exists():
                Zone.objects.create(
                    camera=cam,
                    name="Auto: counter line",
                    kind=Zone.Kind.LINE,
                    geometry=[[0.05, 0.5], [0.95, 0.5]],  # normalised across the frame
                    direction=Zone.Direction.BOTH,
                    is_active=True,
                )
        except Exception:  # noqa: BLE001 — never fail camera create on a side-effect
            pass
        log_action(
            user=self.request.user,
            action="camera.create",
            request=self.request,
            organization=cam.organization,
            metadata={"camera_id": str(cam.id), "name": cam.name},
        )
        # Probe immediately so the dashboard doesn't show "offline" until the next
        # celery-beat tick. Safe to enqueue: idempotent and cheap (one TCP connect).
        try:
            check_camera_health.delay(str(cam.id))
        except Exception:  # noqa: BLE001 — broker hiccup must not break create
            pass

    def perform_update(self, serializer):
        cam = serializer.save()
        log_action(
            user=self.request.user,
            action="camera.update",
            request=self.request,
            organization=cam.organization,
            metadata={"camera_id": str(cam.id)},
        )
        # RTSP URL may have been corrected — re-probe right away.
        try:
            check_camera_health.delay(str(cam.id))
        except Exception:  # noqa: BLE001
            pass

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


class ZoneViewSet(viewsets.ModelViewSet):
    """CRUD for camera Zones (polygon / line / parking_slot).

    Tenant scoping: a user can only see zones whose camera belongs to one of
    their organizations.
    """

    serializer_class = ZoneSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["camera", "kind", "is_active"]

    def get_queryset(self):
        return Zone.objects.filter(
            camera__organization__memberships__user=self.request.user
        ).select_related("camera").distinct()

    def perform_create(self, serializer):
        zone = serializer.save()
        log_action(
            user=self.request.user,
            action="zone.create",
            request=self.request,
            organization=zone.camera.organization,
            metadata={"zone_id": str(zone.id), "kind": zone.kind},
        )


class CameraDiscoveryView(APIView):
    """``POST /api/cameras/discover/`` — find IP cameras on the local network.

    Two methods, returned merged and de-duplicated by IP:

    1. **WS-Discovery** (ONVIF) — UDP multicast probe on 239.255.255.250:3702.
       Pure stdlib, no extra dependency. Most cameras < 5 years old respond.
    2. **TCP fallback** — Optional ``{ "subnet": "192.168.1.0/24" }`` body
       triggers a fast TCP-connect scan on port 554 (RTSP). Works even when
       the host's network blocks multicast.

    Response::

        { "candidates": [
            { "ip": "192.168.1.42", "rtsp_hint": "rtsp://192.168.1.42:554/",
              "manufacturer": "Hikvision", "model": "DS-2CD..." },
            ...
        ] }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        timeout = float(request.data.get("timeout") or 3.0)
        candidates: dict[str, dict] = {}

        for cand in ws_discovery(timeout=timeout):
            candidates[cand["ip"]] = cand

        subnet = (request.data.get("subnet") or "").strip()
        if subnet:
            for cand in probe_subnet(subnet, timeout=timeout):
                # Don't overwrite richer WS-Discovery data.
                candidates.setdefault(cand["ip"], cand)

        log_action(
            user=request.user,
            action="camera.discover",
            request=request,
            metadata={"found": len(candidates), "subnet": subnet},
        )
        return Response({"candidates": list(candidates.values())})


router = DefaultRouter()
router.register(r"health-checks", CameraHealthCheckViewSet, basename="camera-healthcheck")
router.register(r"zones", ZoneViewSet, basename="camera-zone")
router.register(r"", CameraViewSet, basename="camera")

