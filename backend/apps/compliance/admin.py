from django.contrib import admin

from .models import DataProcessingConsent


@admin.register(DataProcessingConsent)
class DataProcessingConsentAdmin(admin.ModelAdmin):
    list_display = (
        "organization", "accepted_by", "terms_version",
        "written_consent", "camera_ownership", "data_processing_terms",
        "revoked_at", "created_at",
    )
    list_filter = ("terms_version", "revoked_at")
    search_fields = ("organization__name", "accepted_by__email")
    readonly_fields = ("ip_address", "user_agent", "created_at", "updated_at")
