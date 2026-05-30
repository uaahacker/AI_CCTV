from rest_framework import permissions, viewsets
from rest_framework.routers import DefaultRouter

from .models import OrganizationSubscription, SubscriptionPlan
from .serializers import OrganizationSubscriptionSerializer, SubscriptionPlanSerializer


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated]


class OrganizationSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizationSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OrganizationSubscription.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()


router = DefaultRouter()
router.register(r"plans", SubscriptionPlanViewSet, basename="subscription-plan")
router.register(r"subscriptions", OrganizationSubscriptionViewSet, basename="org-subscription")
