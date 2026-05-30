from django.contrib import admin

from .models import Camera, CameraHealthCheck


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "status", "is_active", "last_seen_at", "created_at")
    list_filter = ("status", "is_active", "organization")
    search_fields = ("name", "location", "organization__name")
    readonly_fields = ("rtsp_url_encrypted",)


@admin.register(CameraHealthCheck)
class CameraHealthCheckAdmin(admin.ModelAdmin):
    list_display = ("camera", "status", "latency_ms", "checked_at")
    list_filter = ("status",)
    search_fields = ("camera__name",)
