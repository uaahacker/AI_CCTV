from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.audit.utils import log_action

from .models import Membership, Organization
from .serializers import MembershipSerializer, OrganizationSerializer


def _is_owner(user, org: Organization) -> bool:
    return Membership.objects.filter(
        user=user, organization=org, role=Membership.Role.OWNER
    ).exists()


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Organization.objects.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        org = serializer.save()
        log_action(
            user=self.request.user,
            action="organization.create",
            request=self.request,
            organization=org,
            metadata={"name": org.name},
        )

    def perform_update(self, serializer):
        org = serializer.save()
        log_action(
            user=self.request.user,
            action="organization.update",
            request=self.request,
            organization=org,
            metadata={"name": org.name, "retention_days": org.retention_days},
        )

    def destroy(self, request, *args, **kwargs):
        """Soft-delete the org (GDPR \u201cright to erasure\u201d).

        Owner-only. Hard delete happens 7 days later via the
        ``common.purge_deleted_organizations`` Celery task.
        """
        org = self.get_object()
        if not _is_owner(request.user, org):
            raise PermissionDenied("Only an owner can delete an organisation.")
        if org.deleted_at is None:
            org.deleted_at = timezone.now()
            org.is_active = False
            org.save(update_fields=["deleted_at", "is_active", "updated_at"])
            log_action(
                user=request.user,
                action="organization.delete_requested",
                request=request,
                organization=org,
                metadata={"name": org.name},
            )
        return Response(
            {
                "detail": "Organisation marked for deletion. All data will be "
                          "permanently removed in 7 days.",
                "deleted_at": org.deleted_at,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="cancel-deletion")
    def cancel_deletion(self, request, pk=None):
        """Undo a pending soft-delete during the 7-day grace window."""
        org = Organization.all_objects.filter(pk=pk).first()
        if org is None or not _is_owner(request.user, org):
            raise PermissionDenied()
        org.deleted_at = None
        org.is_active = True
        org.save(update_fields=["deleted_at", "is_active", "updated_at"])
        log_action(
            user=request.user,
            action="organization.delete_cancelled",
            request=request,
            organization=org,
        )
        return Response(OrganizationSerializer(org).data)


class MembershipViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Membership.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()


router = DefaultRouter()
# Register most-specific prefix first so it isn't shadowed by the empty prefix.
router.register(r"memberships", MembershipViewSet, basename="membership")
router.register(r"", OrganizationViewSet, basename="organization")
