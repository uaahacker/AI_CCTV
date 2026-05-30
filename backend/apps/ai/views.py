from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.audit.utils import log_action
from apps.common.permissions import IsOrgAdminOrReadOnly

from .models import AIProviderSetting
from .serializers import AIProviderSettingSerializer
from .services import AIProviderFactory


class AIProviderSettingViewSet(viewsets.ModelViewSet):
    """
    CRUD for an organization's AI provider configuration.

    - Only owner/admin members can write (enforced by IsOrgAdminOrReadOnly).
    - The raw api_key is write-only; responses only expose has_api_key /
      masked_api_key.
    """

    serializer_class = AIProviderSettingSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["organization", "provider_type", "is_active"]

    def get_queryset(self):
        return AIProviderSetting.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()

    def perform_create(self, serializer):
        obj = serializer.save()
        log_action(
            user=self.request.user,
            action="ai_provider.create",
            request=self.request,
            organization=obj.organization,
            metadata={"provider_type": obj.provider_type},
        )

    def perform_update(self, serializer):
        obj = serializer.save()
        log_action(
            user=self.request.user,
            action="ai_provider.update",
            request=self.request,
            organization=obj.organization,
            metadata={"provider_type": obj.provider_type},
        )

    @action(detail=True, methods=["post"], url_path="test-connection")
    def test_connection(self, request, pk=None):
        """Synchronously call the provider with a tiny prompt to verify reachability."""
        obj = self.get_object()
        provider = AIProviderFactory.for_settings(obj)
        ok, msg = provider.test_connection()
        log_action(
            user=request.user,
            action="ai_provider.test",
            request=request,
            organization=obj.organization,
            metadata={"ok": ok},
        )
        return Response(
            {"ok": ok, "detail": msg},
            status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST,
        )


router = DefaultRouter()
router.register(r"providers", AIProviderSettingViewSet, basename="ai-provider")
