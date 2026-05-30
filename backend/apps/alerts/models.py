from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.cameras.models import Camera
from apps.common.models import TimeStampedModel
from apps.organizations.models import Organization


VALID_CHANNELS = {"email", "slack", "discord", "webhook", "sms"}


def _validate_channels(value):
    if value is None:
        return
    if not isinstance(value, list):
        raise ValidationError("channels must be a list of channel names.")
    bad = [c for c in value if c not in VALID_CHANNELS]
    if bad:
        raise ValidationError(
            f"Unknown channels: {bad}. Allowed: {sorted(VALID_CHANNELS)}"
        )


class AlertRule(TimeStampedModel):
    class RuleType(models.TextChoices):
        # Counting / business
        PEOPLE_COUNT = "people_count", "People Count"
        CROWD = "crowd_threshold", "Crowd Threshold"
        QUEUE_LENGTH = "queue_length", "Queue Length"
        DWELL_TIME = "dwell_time", "Dwell Time"
        # Security
        INTRUSION = "intrusion", "Intrusion (after-hours)"
        LINE_CROSSING = "line_crossing", "Line Crossing"
        LOITERING = "loitering", "Loitering"
        ABANDONED_OBJECT = "abandoned_object", "Abandoned Object"
        # Parking
        PARKING_OCCUPIED = "parking_occupied", "Parking Slot Occupied"
        PARKING_ILLEGAL = "parking_illegal", "Illegal Parking"
        PARKING_DURATION = "parking_duration", "Parking Duration Exceeded"
        # Infra
        CAMERA_OFFLINE = "camera_offline", "Camera Offline"

    class Condition(models.TextChoices):
        GT = "greater_than", "Greater than"
        LT = "less_than", "Less than"
        EQ = "equals", "Equals"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="alert_rules"
    )
    camera = models.ForeignKey(
        Camera,
        on_delete=models.CASCADE,
        related_name="alert_rules",
        null=True,
        blank=True,
        help_text="Null = rule applies to all cameras in the org.",
    )
    name = models.CharField(max_length=150)
    rule_type = models.CharField(
        max_length=32, choices=RuleType.choices, default=RuleType.PEOPLE_COUNT
    )
    threshold_value = models.FloatField()
    condition = models.CharField(max_length=16, choices=Condition.choices, default=Condition.GT)
    is_active = models.BooleanField(default=True)
    cooldown_seconds = models.PositiveIntegerField(
        default=300, help_text="Minimum seconds between duplicate alerts."
    )

    # --- Notification routing (multi-channel) ---------------------------
    notification_email = models.EmailField(
        blank=True,
        help_text="Legacy single-recipient email. Prefer channels/channel_config.",
    )
    channels = models.JSONField(
        default=list,
        blank=True,
        validators=[_validate_channels],
        help_text='List of channels: ["email","slack","discord","webhook","sms"].',
    )
    channel_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Per-channel config, e.g. '
            '{"slack": {"webhook_url": "..."}, '
            '"discord": {"webhook_url": "..."}, '
            '"webhook": {"url": "...", "auth_token": "..."}, '
            '"email": {"to": "ops@example.com"}, '
            '"sms": {"to": "+15551234567"}}'
        ),
    )

    # --- Time-window predicate (org-local time) -------------------------
    active_from = models.CharField(max_length=5, blank=True, help_text="HH:MM, e.g. 18:00")
    active_to = models.CharField(max_length=5, blank=True, help_text="HH:MM, e.g. 20:00")
    days_of_week = models.JSONField(
        default=list, blank=True,
        help_text="List of ISO weekday ints 1=Mon..7=Sun. Empty = every day."
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} ({self.rule_type} {self.condition} {self.threshold_value})"


class Alert(TimeStampedModel):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NEW = "new", "New"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="alerts"
    )
    camera = models.ForeignKey(
        Camera, on_delete=models.CASCADE, related_name="alerts", null=True, blank=True
    )
    alert_rule = models.ForeignKey(
        AlertRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="alerts"
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.WARNING)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    metadata = models.JSONField(default=dict, blank=True)
    ai_summary = models.TextField(
        blank=True,
        help_text=(
            "Optional LLM-generated human summary. Populated asynchronously "
            "if the organization has an active AI provider configured."
        ),
    )

    # --- Optional short evidence clip -----------------------------------
    # Per architecture: NEVER store full footage. Only a 1-5 s compressed clip
    # tied to a validated security alert. Path is relative to MEDIA_ROOT.
    clip_path = models.CharField(
        max_length=500, blank=True,
        help_text="Relative path to 1-5 s evidence clip under MEDIA_ROOT. Optional."
    )
    clip_duration_s = models.PositiveSmallIntegerField(default=0)

    # --- Delivery audit -------------------------------------------------
    delivery_log = models.JSONField(
        default=dict, blank=True,
        help_text='Per-channel delivery results, e.g. {"slack": {"ok": true}}'
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"
