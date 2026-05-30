from __future__ import annotations

from django.db import models

from apps.cameras.models import Camera
from apps.common.models import TimeStampedModel
from apps.organizations.models import Organization


class DetectionEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        PEOPLE_COUNT = "people_count", "People Count"
        INTRUSION = "intrusion", "Intrusion"
        CROWD_THRESHOLD = "crowd_threshold", "Crowd Threshold"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="detection_events"
    )
    camera = models.ForeignKey(
        Camera, on_delete=models.CASCADE, related_name="detection_events"
    )
    event_type = models.CharField(
        max_length=32, choices=EventType.choices, default=EventType.PEOPLE_COUNT
    )
    people_count = models.PositiveIntegerField(default=0)
    confidence = models.FloatField(default=0.0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["camera", "-created_at"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} cam={self.camera_id} n={self.people_count}"
