from __future__ import annotations

from django.db import models

from apps.cameras.models import Camera
from apps.common.models import TimeStampedModel
from apps.organizations.models import Organization


class DetectionEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        # Core
        PEOPLE_COUNT = "people_count", "People Count"
        INTRUSION = "intrusion", "Intrusion"
        CROWD_THRESHOLD = "crowd_threshold", "Crowd Threshold"
        # Tracking / zone analytics (Phase 9)
        ZONE_ENTRY = "zone_entry", "Zone Entry"
        ZONE_EXIT = "zone_exit", "Zone Exit"
        LINE_CROSSING = "line_crossing", "Line Crossing"
        LOITERING = "loitering", "Loitering"
        ABANDONED_OBJECT = "abandoned_object", "Abandoned Object"
        QUEUE_LENGTH = "queue_length", "Queue Length"
        # Parking (Phase 9)
        PARKING_OCCUPIED = "parking_occupied", "Parking Slot Occupied"
        PARKING_VACATED = "parking_vacated", "Parking Slot Vacated"
        PARKING_ILLEGAL = "parking_illegal", "Illegal Parking"
        PARKING_DURATION = "parking_duration", "Parking Duration Exceeded"

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
    # Extra context: track_id, zone_id, dwell_seconds, direction, clip_path, ...
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


class HeatmapBucket(TimeStampedModel):
    """Aggregated occupancy density per camera, hour, grid cell.

    The CV worker emits centroid points and we bucket them into a 16×16 grid
    so we never store individual coordinates long-term.
    """

    GRID = 16

    camera = models.ForeignKey(
        Camera, on_delete=models.CASCADE, related_name="heatmap_buckets"
    )
    hour_bucket = models.DateTimeField(db_index=True)
    grid_x = models.PositiveSmallIntegerField()
    grid_y = models.PositiveSmallIntegerField()
    weight = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-hour_bucket",)
        constraints = [
            models.UniqueConstraint(
                fields=("camera", "hour_bucket", "grid_x", "grid_y"),
                name="heatmap_bucket_unique",
            )
        ]
        indexes = [
            models.Index(fields=["camera", "-hour_bucket"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.camera_id}@{self.hour_bucket:%Y-%m-%d %H} ({self.grid_x},{self.grid_y})={self.weight}"


class ParkingSlotState(TimeStampedModel):
    """Latest occupancy state for each parking slot zone.

    One row per Zone(kind=PARKING_SLOT). Updated by the parking detector.
    """

    class State(models.TextChoices):
        FREE = "free", "Free"
        OCCUPIED = "occupied", "Occupied"
        ILLEGAL = "illegal", "Illegal"

    zone = models.OneToOneField(
        "cameras.Zone", on_delete=models.CASCADE, related_name="parking_state"
    )
    state = models.CharField(max_length=16, choices=State.choices, default=State.FREE)
    since = models.DateTimeField(null=True, blank=True)
    vehicle_track_id = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ("zone__camera", "zone__name")

    def __str__(self) -> str:  # pragma: no cover
        return f"slot {self.zone_id} = {self.state}"
