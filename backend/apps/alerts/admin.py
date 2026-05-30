from django.contrib import admin

from .models import Alert, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "camera", "rule_type", "condition", "threshold_value", "is_active")
    list_filter = ("rule_type", "is_active", "organization")
    search_fields = ("name",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("created_at", "title", "severity", "status", "camera", "organization")
    list_filter = ("severity", "status", "organization")
    search_fields = ("title", "message")
    date_hierarchy = "created_at"
