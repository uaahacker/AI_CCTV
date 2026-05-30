from django.contrib import admin

from .models import DetectionEvent, HeatmapBucket, ParkingSlotState


@admin.register(DetectionEvent)
class DetectionEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "camera", "event_type", "people_count", "confidence")
    list_filter = ("event_type", "organization")
    search_fields = ("camera__name",)
    date_hierarchy = "created_at"


@admin.register(HeatmapBucket)
class HeatmapBucketAdmin(admin.ModelAdmin):
    list_display = ("camera", "hour_bucket", "grid_x", "grid_y", "weight")
    list_filter = ("camera",)
    date_hierarchy = "hour_bucket"


@admin.register(ParkingSlotState)
class ParkingSlotStateAdmin(admin.ModelAdmin):
    list_display = ("zone", "state", "since", "vehicle_track_id", "updated_at")
    list_filter = ("state",)
