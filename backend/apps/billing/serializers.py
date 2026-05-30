from rest_framework import serializers

from .models import OrganizationSubscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = (
            "id",
            "name",
            "tier",
            "price_per_camera_monthly",
            "max_cameras",
            "features",
            "is_active",
        )
        read_only_fields = fields


class OrganizationSubscriptionSerializer(serializers.ModelSerializer):
    plan_detail = SubscriptionPlanSerializer(source="plan", read_only=True)

    class Meta:
        model = OrganizationSubscription
        fields = (
            "id",
            "organization",
            "plan",
            "plan_detail",
            "status",
            "seats_cameras",
            "current_period_end",
        )
        read_only_fields = ("id", "plan_detail")
