"""MFA enrolment endpoints (separate file to keep ``views.py`` readable)."""
from __future__ import annotations

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.utils import log_action
from apps.common.security import decrypt_str, encrypt_str

from . import mfa as mfa_helpers
from .models import MFADevice


class MFAEnrollView(APIView):
    """POST → generate a fresh TOTP secret, return the otpauth URI + plaintext
    recovery codes. The device stays *unconfirmed* until the user posts a
    valid TOTP code to ``/auth/mfa/confirm/``.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        # Delete any old unconfirmed device so re-enrolment is idempotent.
        MFADevice.objects.filter(user=user, confirmed_at__isnull=True).delete()
        if MFADevice.objects.filter(user=user, confirmed_at__isnull=False).exists():
            return Response(
                {"detail": "MFA already enabled — disable it first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        secret = mfa_helpers.generate_secret()
        recovery_plain = mfa_helpers.generate_recovery_codes()
        recovery_hashed = mfa_helpers.hash_recovery_codes(recovery_plain)

        MFADevice.objects.create(
            user=user,
            secret_encrypted=encrypt_str(secret),
            recovery_codes=recovery_hashed,
        )

        log_action(user=user, action="mfa.enroll.start", request=request, metadata={})

        return Response(
            {
                "otpauth_uri": mfa_helpers.provisioning_uri(
                    secret, account_name=user.email
                ),
                "secret": secret,  # for manual entry
                "recovery_codes": recovery_plain,
                "detail": (
                    "Scan the otpauth URI in your authenticator, then POST the "
                    "6-digit code to /api/auth/mfa/confirm/ to finish enrolment. "
                    "Recovery codes are shown ONCE — store them safely."
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class MFAConfirmView(APIView):
    """POST ``{"code": "123456"}`` to finalise enrolment."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get("code") or "").strip()
        device = MFADevice.objects.filter(
            user=request.user, confirmed_at__isnull=True
        ).first()
        if device is None:
            return Response(
                {"detail": "No pending MFA enrolment. POST /auth/mfa/enroll/ first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        secret = decrypt_str(device.secret_encrypted)
        if not mfa_helpers.totp_verify(secret, code):
            return Response(
                {"detail": "Invalid code — try again with the next refresh."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device.confirmed_at = timezone.now()
        device.last_used_at = timezone.now()
        device.save(update_fields=["confirmed_at", "last_used_at", "updated_at"])

        log_action(
            user=request.user, action="mfa.enroll.confirm", request=request, metadata={}
        )
        return Response({"detail": "MFA enabled."}, status=status.HTTP_200_OK)


class MFAStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        device = MFADevice.objects.filter(user=request.user).first()
        if device is None:
            return Response({"enabled": False, "pending": False})
        return Response(
            {
                "enabled": device.confirmed_at is not None,
                "pending": device.confirmed_at is None,
                "recovery_codes_remaining": len(device.recovery_codes or []),
                "last_used_at": device.last_used_at,
            }
        )


class MFADisableView(APIView):
    """POST ``{"code": "..."}`` (valid TOTP or recovery code) to disable MFA."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        device = MFADevice.objects.filter(
            user=request.user, confirmed_at__isnull=False
        ).first()
        if device is None:
            return Response(
                {"detail": "MFA is not enabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        code = (request.data.get("code") or "").strip()
        secret = decrypt_str(device.secret_encrypted)
        if not (
            mfa_helpers.totp_verify(secret, code)
            or mfa_helpers.consume_recovery_code(device, code)
        ):
            return Response(
                {"detail": "Invalid code."}, status=status.HTTP_400_BAD_REQUEST
            )
        device.delete()
        log_action(
            user=request.user, action="mfa.disable", request=request, metadata={}
        )
        return Response({"detail": "MFA disabled."}, status=status.HTTP_200_OK)
