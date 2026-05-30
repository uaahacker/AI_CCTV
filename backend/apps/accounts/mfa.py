"""TOTP (RFC 6238) MFA helpers — pure stdlib, no third-party deps.

This module owns three things:

1. The ``MFADevice`` ORM model (defined in ``models.py``) — stores the
   per-user encrypted base32 secret and a list of one-time recovery codes.
2. Helpers to generate / validate TOTP codes and provisioning URIs that any
   standard authenticator app (Google Authenticator, Authy, 1Password,
   FreeOTP, …) understands.
3. A short-lived "MFA challenge" token used to bridge the two-step login
   flow: ``/auth/token/`` returns a challenge when the user has MFA enabled,
   the client posts ``challenge + 6-digit code`` to ``/auth/mfa/verify/``,
   and we hand back the real JWT pair.

The challenge is just Django's signed timestamped string, so we don't need
to persist it server-side.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Iterable
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

_SIGNER_SALT = "apps.accounts.mfa.challenge"

# ---------------------------------------------------------------------------
# Base32 secret helpers
# ---------------------------------------------------------------------------
def generate_secret(length_bytes: int = 20) -> str:
    """Return a fresh base32-encoded TOTP secret (default 160-bit, the
    RFC 4226 recommendation).
    """
    return base64.b32encode(secrets.token_bytes(length_bytes)).decode("ascii").rstrip("=")


def _b32_decode(secret: str) -> bytes:
    # Pad the secret back to a multiple of 8 chars before decoding.
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded, casefold=True)


# ---------------------------------------------------------------------------
# TOTP (RFC 6238)
# ---------------------------------------------------------------------------
def _hotp(secret_bytes: bytes, counter: int, digits: int = 6) -> str:
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return str(truncated % (10 ** digits)).zfill(digits)


def totp_now(secret: str, *, step: int = 30, digits: int = 6, t: float | None = None) -> str:
    """Generate the TOTP value for ``secret`` at unix-time ``t`` (default: now)."""
    if t is None:
        t = time.time()
    counter = int(t // step)
    return _hotp(_b32_decode(secret), counter, digits=digits)


def totp_verify(
    secret: str,
    code: str,
    *,
    step: int = 30,
    digits: int = 6,
    drift_steps: int = 1,
    t: float | None = None,
) -> bool:
    """Constant-time TOTP verify with ±``drift_steps`` tolerance."""
    if not code or not code.isdigit() or len(code) != digits:
        return False
    if t is None:
        t = time.time()
    counter = int(t // step)
    secret_bytes = _b32_decode(secret)
    for delta in range(-drift_steps, drift_steps + 1):
        candidate = _hotp(secret_bytes, counter + delta, digits=digits)
        if hmac.compare_digest(candidate, code):
            return True
    return False


def provisioning_uri(secret: str, *, account_name: str, issuer: str | None = None) -> str:
    """Build the ``otpauth://totp/…`` URI an authenticator app reads from a QR."""
    issuer = issuer or getattr(settings, "MFA_ISSUER", "AI CCTV Analytics")
    label = f"{quote(issuer)}:{quote(account_name)}"
    query = f"secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    return f"otpauth://totp/{label}?{query}"


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------
def generate_recovery_codes(n: int = 10) -> list[str]:
    """Return n 10-character base32 single-use recovery codes."""
    out = []
    for _ in range(n):
        raw = secrets.token_bytes(6)
        code = base64.b32encode(raw).decode("ascii").rstrip("=")[:10]
        out.append(code)
    return out


def hash_recovery_codes(codes: Iterable[str]) -> list[str]:
    """Hash recovery codes for storage (we never store plaintext)."""
    return [hashlib.sha256(c.encode("utf-8")).hexdigest() for c in codes]


def consume_recovery_code(device, code: str) -> bool:
    """If ``code`` matches an unused recovery hash, remove it and return True."""
    if not code:
        return False
    h = hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()
    hashes = list(device.recovery_codes or [])
    if h in hashes:
        hashes.remove(h)
        device.recovery_codes = hashes
        device.save(update_fields=["recovery_codes", "updated_at"])
        return True
    return False


# ---------------------------------------------------------------------------
# Convenience: per-user lookups
# ---------------------------------------------------------------------------
def get_active_device(user) -> "object | None":
    """Return the user's confirmed MFA device, or None."""
    # Imported lazily to avoid circular import at module load.
    from .models import MFADevice  # noqa: WPS433
    if not getattr(user, "is_authenticated", False):
        return None
    return MFADevice.objects.filter(user=user, confirmed_at__isnull=False).first()


def user_has_active_mfa(user) -> bool:
    return get_active_device(user) is not None


# ---------------------------------------------------------------------------
# Two-step login bridge: signed challenge token
# ---------------------------------------------------------------------------
def build_mfa_challenge(user) -> str:
    """Return a short-lived signed token that proves the password was valid."""
    signer = TimestampSigner(salt=_SIGNER_SALT)
    return signer.sign(str(user.pk))


def verify_mfa_challenge(token: str, code: str) -> "User":
    """Validate the challenge + TOTP code and return the user.

    Raises ``AuthenticationFailed`` on any problem.
    """
    signer = TimestampSigner(salt=_SIGNER_SALT)
    max_age = int(getattr(settings, "MFA_CHALLENGE_LIFETIME_SECONDS", 300) or 300)
    try:
        user_pk = signer.unsign(token, max_age=max_age)
    except SignatureExpired as exc:
        raise AuthenticationFailed("MFA challenge expired — log in again.") from exc
    except BadSignature as exc:
        raise AuthenticationFailed("Invalid MFA challenge.") from exc

    try:
        user = User.objects.get(pk=user_pk, is_active=True)
    except User.DoesNotExist as exc:  # pragma: no cover - defensive
        raise AuthenticationFailed("User no longer exists.") from exc

    device = get_active_device(user)
    if device is None:
        raise AuthenticationFailed("MFA is not configured for this user.")

    from apps.common.security import decrypt_str  # noqa: WPS433
    secret = decrypt_str(device.secret_encrypted)

    if totp_verify(secret, code):
        return user
    if consume_recovery_code(device, code):
        return user
    raise AuthenticationFailed("Invalid MFA code.")


def issue_tokens_for_user(user) -> dict[str, str]:
    """Mint a real JWT pair for ``user``. Used after MFA verification."""
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}
