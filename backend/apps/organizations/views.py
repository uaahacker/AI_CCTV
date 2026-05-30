from rest_framework import permissions, viewsets
from rest_framework.routers import DefaultRouter

from apps.audit.utils import log_action

from .models import Membership, Organization
from .serializers import MembershipSerializer, OrganizationSerializer


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
