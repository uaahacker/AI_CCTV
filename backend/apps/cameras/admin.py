from django.contrib import admin

from .models import Camera, CameraHealthCheck, Zone


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


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "camera", "kind", "direction", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "camera__name")
