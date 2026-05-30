from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.security import decrypt_str, encrypt_str
from apps.organizations.models import Organization


class Camera(TimeStampedModel):
    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        ERROR = "error", "Error"

    class RecordingPolicy(models.TextChoices):
        OFF = "off", "No recording"
        CONTINUOUS = "continuous", "Continuous (rolling)"
        MOTION = "motion", "Motion-triggered"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="cameras"
    )
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=200, blank=True)
    # Encrypted at rest. Access through `rtsp_url` property.
    rtsp_url_encrypted = models.TextField()
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNKNOWN)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    # Recording library — promoted from HLS segments by the streamer.
    recording_policy = models.CharField(
        max_length=16,
        choices=RecordingPolicy.choices,
        default=RecordingPolicy.OFF,
        help_text=(
            "Whether to keep on-disk MP4 recordings (subject to the "
            "organisation's RECORDING_RETENTION_DAYS)."
        ),
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.organization.name})"

    # --- Encrypted RTSP URL helpers ------------------------------------
    @property
    def rtsp_url(self) -> str:
        return decrypt_str(self.rtsp_url_encrypted)

    @rtsp_url.setter
    def rtsp_url(self, value: str) -> None:
        self.rtsp_url_encrypted = encrypt_str(value or "")


class CameraHealthCheck(TimeStampedModel):
    camera = models.ForeignKey(
        Camera, on_delete=models.CASCADE, related_name="health_checks"
    )
    status = models.CharField(max_length=16, choices=Camera.Status.choices)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-checked_at",)
        indexes = [models.Index(fields=["camera", "-checked_at"])]

    def __str__(self) -> str:
        return f"{self.camera.name} @ {self.checked_at:%Y-%m-%d %H:%M} = {self.status}"


class Zone(TimeStampedModel):
    """A named geometry overlaid on a camera frame.

    Coordinates are *normalised* to ``[0, 1]`` so the same zone keeps its
    meaning when the stream's resolution changes. The pipeline scales them
    to pixel space at runtime.

    Kinds:
    - ``polygon`` — closed region used for queue length, dwell-time,
      loitering, intrusion, abandoned-object detection. ``geometry`` is a
      list of ``[x, y]`` pairs (length >= 3).
    - ``line`` — directional tripwire used for entry/exit and line-crossing.
      ``geometry`` is exactly two ``[x, y]`` points. ``direction`` controls
      which side counts as "in".
    - ``parking_slot`` — single bay used by the parking analytics. Same
      shape as a polygon; the parking detector treats it specially.
    """

    class Kind(models.TextChoices):
        POLYGON = "polygon", "Polygon"
        LINE = "line", "Line / tripwire"
        PARKING_SLOT = "parking_slot", "Parking slot"

    class Direction(models.TextChoices):
        NONE = "none", "Bi-directional"
        IN = "in", "Crossing IN counts"
        OUT = "out", "Crossing OUT counts"
        BOTH = "both", "Count both directions"

    camera = models.ForeignKey(
        Camera, on_delete=models.CASCADE, related_name="zones"
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.POLYGON)
    # Validated by Zone.clean(): polygon >= 3 points, line == 2 points.
    geometry = models.JSONField(
        help_text='Normalised coords [[x,y],...] with x,y in [0,1].'
    )
    direction = models.CharField(
        max_length=10, choices=Direction.choices, default=Direction.NONE,
        help_text="Only meaningful for LINE zones."
    )
    is_active = models.BooleanField(default=True)
    # Free-form config: dwell_seconds, abandoned_seconds, max_occupancy, etc.
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("camera", "name")
        indexes = [
            models.Index(fields=["camera", "is_active"]),
            models.Index(fields=["kind"]),
        ]

    def __str__(self) -> str:
        return f"{self.camera.name}::{self.name} ({self.kind})"

    def clean(self):
        from django.core.exceptions import ValidationError

        geom = self.geometry
        if not isinstance(geom, list) or not geom:
            raise ValidationError("geometry must be a non-empty list of [x, y] pairs.")
        for p in geom:
            if (
                not isinstance(p, (list, tuple))
                or len(p) != 2
                or not all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0 for c in p)
            ):
                raise ValidationError("Each point must be [x, y] with 0 <= value <= 1.")
        if self.kind == self.Kind.LINE and len(geom) != 2:
            raise ValidationError("A LINE zone requires exactly two points.")
        if self.kind in {self.Kind.POLYGON, self.Kind.PARKING_SLOT} and len(geom) < 3:
            raise ValidationError("A polygon/parking_slot needs at least 3 points.")


class Recording(TimeStampedModel):
    """A finished MP4 segment promoted from the HLS playlist.

    The streamer rotates HLS segments every ~2 s. A periodic Celery task
    (``cameras.promote_recordings``) concatenates the segments older than
    one rotation window into a single hourly MP4 under
    ``MEDIA_ROOT/recordings/<camera_id>/<YYYY>/<MM>/<DD>/<HH>.mp4``.

    Files are deleted by ``common.purge_expired_data`` once older than
    ``settings.RECORDING_RETENTION_DAYS``.
    """

    class Kind(models.TextChoices):
        CONTINUOUS = "continuous", "Continuous"
        MOTION = "motion", "Motion"
        EVIDENCE = "evidence", "Evidence clip"

    camera = models.ForeignKey(
        Camera, on_delete=models.CASCADE, related_name="recordings"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.CONTINUOUS)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_s = models.PositiveIntegerField(default=0)
    size_bytes = models.PositiveBigIntegerField(default=0)
    # Relative to MEDIA_ROOT. Resolved by the signed-media view.
    file_path = models.CharField(max_length=500)

    class Meta:
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=["camera", "-started_at"]),
            models.Index(fields=["kind", "-started_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.camera_id} {self.kind} @ {self.started_at:%Y-%m-%d %H:%M}"

