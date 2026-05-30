from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class OrganizationManager(models.Manager):
    """Default manager hides soft-deleted organisations.

    Use ``Organization.all_objects`` to see everything (e.g. the retention
    purge task that hard-deletes after the grace period).
    """

    def get_queryset(self):  # type: ignore[override]
        return super().get_queryset().filter(deleted_at__isnull=True)


class Organization(TimeStampedModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    is_active = models.BooleanField(default=True)

    # --- Data retention (GDPR / customer policy) -----------------------
    # Detection events, alerts, heatmaps and recordings older than this
    # are deleted nightly by ``common.purge_expired_data``. Audit logs
    # use a separate, longer retention (settings.AUDIT_RETENTION_DAYS).
    retention_days = models.PositiveIntegerField(
        default=90,
        help_text="How long (days) to keep analytics, alerts and clips.",
    )

    # --- Soft delete (GDPR \u201cright to erasure\u201d) ----------------------------
    # Setting ``deleted_at`` hides the org from every list endpoint and
    # blocks new writes. After a 7-day grace window the row, all related
    # models and the on-disk media tree are hard-deleted by
    # ``common.purge_deleted_organizations``.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = OrganizationManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class Membership(TimeStampedModel):
    """RBAC link between a User and an Organization."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        OPERATOR = "operator", "Operator"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.VIEWER)

    class Meta:
        unique_together = ("user", "organization")
        ordering = ("organization", "user")

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"
