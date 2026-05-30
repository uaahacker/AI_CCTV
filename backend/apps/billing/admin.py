from django.contrib import admin

from .models import OrganizationSubscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "tier", "price_per_camera_monthly", "max_cameras", "is_active")


@admin.register(OrganizationSubscription)
class OrganizationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "seats_cameras", "current_period_end")
    list_filter = ("status", "plan")
