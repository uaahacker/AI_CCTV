from __future__ import annotations

from django.conf import settings
from rest_framework import mixins, permissions, viewsets
from rest_framework.routers import DefaultRouter

from apps.common.permissions import IsOrgAdminOrReadOnly

from .models import DataProcessingConsent
from .serializers import DataProcessingConsentSerializer


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class DataProcessingConsentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """List + create only — consent records are immutable once signed."""
    serializer_class = DataProcessingConsentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOrReadOnly]

    def get_queryset(self):
        return (
            DataProcessingConsent.objects
            .filter(organization__memberships__user=self.request.user)
            .distinct()
        )

    def perform_create(self, serializer):
        serializer.save(
            accepted_by=self.request.user,
            ip_address=_client_ip(self.request),
            user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:500],
            terms_version=getattr(settings, "CONSENT_TERMS_VERSION", "1.0"),
        )


router = DefaultRouter()
router.register(r"consents", DataProcessingConsentViewSet, basename="consent")
