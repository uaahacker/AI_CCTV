"""
GDPR-style legal-compliance records.

`DataProcessingConsent` is the single source of truth that an authorised
representative of the customer organisation has affirmed:
  1.  Written consent to deploy CCTV analytics on the listed cameras.
  2.  Ownership of (or contractual right to operate) the cameras.
  3.  Acceptance of our data-processing terms:
        "We process footage only for analytics. Ownership of the footage
         remains with the client; no raw video is persisted by us;
         facial recognition is disabled by default."

The middleware `ConsentEnforcementMiddleware` blocks write APIs to camera
streams and analytics endpoints when no current consent exists.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.organizations.models import Organization


class DataProcessingConsent(TimeStampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="consents"
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consents_signed",
    )

    # Three required affirmations.
    written_consent = models.BooleanField(default=False)
    camera_ownership = models.BooleanField(default=False)
    data_processing_terms = models.BooleanField(default=False)

    # Provenance.
    terms_version = models.CharField(max_length=32, default="1.0")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)

    # If revoked, set this — the org is then non-compliant until a new
    # consent row is created.
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Consent v{self.terms_version} for {self.organization_id} by {self.accepted_by_id}"

    @property
    def is_valid(self) -> bool:
        return (
            self.written_consent
            and self.camera_ownership
            and self.data_processing_terms
            and self.revoked_at is None
        )
