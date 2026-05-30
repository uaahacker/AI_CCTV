from django.contrib import admin

from .models import AIProviderSetting


@admin.register(AIProviderSetting)
class AIProviderSettingAdmin(admin.ModelAdmin):
    list_display = ("organization", "provider_type", "model_name", "is_active", "updated_at")
    list_filter = ("provider_type", "is_active")
    search_fields = ("organization__name", "model_name", "display_name")
    # Never expose the encrypted blob or the raw key in the admin form.
    exclude = ("api_key_encrypted",)
    readonly_fields = ("created_at", "updated_at", "masked_api_key_display")

    def masked_api_key_display(self, obj):
        return obj.masked_api_key or "(not set)"

    masked_api_key_display.short_description = "API key (masked)"
