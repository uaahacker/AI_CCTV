"""Custom user model — email-based login."""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields.get("is_staff") or not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class MFADevice(models.Model):
    """A user's TOTP-based MFA enrolment.

    The base32 secret is Fernet-encrypted at rest using the project's
    ``FIELD_ENCRYPTION_KEY``. Recovery codes are stored as SHA-256 hashes
    only — the plaintext is shown once at enrolment time and never again.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="mfa_device"
    )
    secret_encrypted = models.TextField()
    # JSON list of sha256 hex digests; popped one by one on use.
    recovery_codes = models.JSONField(default=list, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "MFA device"
        verbose_name_plural = "MFA devices"

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"MFA<{self.user.email}>"

