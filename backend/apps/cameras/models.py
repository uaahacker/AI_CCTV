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
