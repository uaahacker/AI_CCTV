from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel
from apps.organizations.models import Organization


class SubscriptionPlan(TimeStampedModel):
    class Tier(models.TextChoices):
        BASIC = "basic", "Basic"
        PRO = "pro", "Pro"
        ENTERPRISE = "enterprise", "Enterprise"

    name = models.CharField(max_length=80)
    tier = models.CharField(max_length=20, choices=Tier.choices, unique=True)
    price_per_camera_monthly = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_cameras = models.PositiveIntegerField(default=10)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("price_per_camera_monthly",)

    def __str__(self) -> str:
        return f"{self.name} ({self.tier})"


class OrganizationSubscription(TimeStampedModel):
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        CANCELED = "canceled", "Canceled"

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIAL)
    seats_cameras = models.PositiveIntegerField(default=0)
    current_period_end = models.DateTimeField(null=True, blank=True)
    # Real Stripe integration is deferred. Keep placeholders for future use.
    stripe_customer_id = models.CharField(max_length=120, blank=True)
    stripe_subscription_id = models.CharField(max_length=120, blank=True)

    def __str__(self) -> str:
        return f"{self.organization} -> {self.plan} ({self.status})"
