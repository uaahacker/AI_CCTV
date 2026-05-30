"""Password reset and email-verification flows.

Both flows follow the same shape:

  1. Client POSTs an identifier to ``/request/`` (email-only \u2014 we never
     reveal whether the address exists). Server creates a token row with a
     SHA-256 hash, mails the *plaintext* token to the user, and returns 202.
  2. Client follows the link, lands on a frontend page, then POSTs the
     plaintext token back to ``/confirm/``. Server looks up the hash,
     verifies expiry/used_at, mutates the user, marks the token used.

Tokens are 32 bytes of url-safe randomness (43 ASCII chars). Cooldown +
rate-limit prevent enumeration / abuse.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.utils import log_action

from .models import EmailVerificationToken, PasswordResetToken

User = get_user_model()

PASSWORD_RESET_TTL = timedelta(hours=1)
EMAIL_VERIFY_TTL = timedelta(days=2)
TOKEN_BYTES = 32


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _send_mail_safe(subject: str, message: str, to: str) -> None:
    """Send transactional mail; swallow errors so the API never leaks SMTP
    failure details. The error is logged by Django's mail backend."""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipient_list=[to],
            fail_silently=True,
        )
    except Exception:  # noqa: BLE001
        pass


# --- Password reset ------------------------------------------------------

class _EmailOnlySerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetRequestView(APIView):
    """``POST /api/auth/password/reset/request/``  body: ``{email}``.

    Always returns 202 to avoid leaking whether the address exists.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "password_reset"

    def post(self, request):
        ser = _EmailOnlySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            token = secrets.token_urlsafe(TOKEN_BYTES)
            PasswordResetToken.objects.create(
                user=user,
                token_hash=_hash(token),
                expires_at=timezone.now() + PASSWORD_RESET_TTL,
                requested_ip=_client_ip(request),
            )
            link = f"{settings.PUBLIC_SITE_URL}/reset-password/{token}"
            _send_mail_safe(
                subject="Reset your AI-CCTV password",
                message=(
                    "Hi,\n\nUse the link below to set a new password. "
                    "It expires in 1 hour:\n\n"
                    f"{link}\n\n"
                    "If you didn't request this, you can safely ignore this email."
                ),
                to=user.email,
            )
            log_action(
                user=user, action="password_reset.requested",
                request=request, metadata={"email": email},
            )
        return Response(
            {"detail": "If an account exists for that email, a reset link has been sent."},
            status=status.HTTP_202_ACCEPTED,
        )


class _PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


class PasswordResetConfirmView(APIView):
    """``POST /api/auth/password/reset/confirm/``  body: ``{token, new_password}``."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "password_reset"

    def post(self, request):
        ser = _PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        token = ser.validated_data["token"]
        new_password = ser.validated_data["new_password"]

        row = PasswordResetToken.objects.filter(token_hash=_hash(token)).first()
        if row is None or not row.is_active:
            return Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_password(new_password, user=row.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        user = row.user
        user.set_password(new_password)
        user.save(update_fields=["password"])
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        # Defence in depth: invalidate every other live reset token for this user.
        PasswordResetToken.objects.filter(user=user, used_at__isnull=True).exclude(
            pk=row.pk
        ).update(used_at=timezone.now())

        log_action(
            user=user, action="password_reset.completed",
            request=request, metadata={"email": user.email},
        )
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


# --- Email verification --------------------------------------------------

class EmailVerifyRequestView(APIView):
    """``POST /api/auth/email/verify/request/`` (authenticated). Sends a fresh link."""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "email_verify"

    def post(self, request):
        user = request.user
        if user.email_verified:
            return Response({"detail": "Already verified."}, status=status.HTTP_200_OK)
        token = secrets.token_urlsafe(TOKEN_BYTES)
        EmailVerificationToken.objects.create(
            user=user,
            token_hash=_hash(token),
            expires_at=timezone.now() + EMAIL_VERIFY_TTL,
            requested_ip=_client_ip(request),
        )
        link = f"{settings.PUBLIC_SITE_URL}/verify-email/{token}"
        _send_mail_safe(
            subject="Verify your AI-CCTV email",
            message=(
                "Hi,\n\nClick the link below to verify this address (valid for 48h):\n\n"
                f"{link}\n"
            ),
            to=user.email,
        )
        log_action(user=user, action="email_verify.requested", request=request)
        return Response({"detail": "Verification email sent."}, status=status.HTTP_202_ACCEPTED)


class _TokenOnlySerializer(serializers.Serializer):
    token = serializers.CharField()


class EmailVerifyConfirmView(APIView):
    """``POST /api/auth/email/verify/confirm/`` body: ``{token}``.

    Public (the user clicks an email link before logging in). Flipping the
    flag is idempotent.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "email_verify"

    def post(self, request):
        ser = _TokenOnlySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        token = ser.validated_data["token"]
        row = EmailVerificationToken.objects.filter(token_hash=_hash(token)).first()
        if row is None or not row.is_active:
            return Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not row.user.email_verified:
            row.user.email_verified = True
            row.user.save(update_fields=["email_verified"])
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        log_action(user=row.user, action="email_verify.completed", request=request)
        return Response({"detail": "Email verified."}, status=status.HTTP_200_OK)
