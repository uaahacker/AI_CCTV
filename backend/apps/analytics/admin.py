from django.contrib import admin

from .models import DetectionEvent


@admin.register(DetectionEvent)
class DetectionEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "camera", "event_type", "people_count", "confidence")
    list_filter = ("event_type", "organization")
    search_fields = ("camera__name",)
    date_hierarchy = "created_at"
