from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    OrganizationSubscriptionViewSet,
    StripeWebhookView,
    SubscriptionPlanViewSet,
)

router = DefaultRouter()
router.register(r"plans", SubscriptionPlanViewSet, basename="subscription-plan")
router.register(r"subscriptions", OrganizationSubscriptionViewSet, basename="org-subscription")

urlpatterns = router.urls + [
    path("webhook/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
