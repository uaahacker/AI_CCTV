"""HMAC-signed media URLs.

We don't trust nginx to authenticate users for HLS playlists or evidence
clips — every request that wants to read something under MEDIA_ROOT must
present a token issued by Django after the caller's JWT was validated.

Tokens are stateless: ``HMAC-SHA256(MEDIA_SIGNING_KEY, "<path>|<expires>")``
so we can verify them without a DB lookup. Expiry is a Unix timestamp.

Example::

    from apps.common.signing import sign_media_path, verify_media_token
    token, expires = sign_media_path("hls/<camera_id>/index.m3u8")
    # ...later, on a public endpoint:
    if not verify_media_token("hls/<camera_id>/index.m3u8", token, expires):
        raise PermissionDenied
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Tuple

from django.conf import settings


def _key() -> bytes:
    raw = getattr(settings, "MEDIA_SIGNING_KEY", "") or settings.SECRET_KEY
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def _normalize(path: str) -> str:
    # Tokens are bound to a relative, posix-style path under MEDIA_ROOT.
    return path.lstrip("/").replace("\\", "/")


def sign_media_path(path: str, ttl_seconds: int | None = None) -> Tuple[str, int]:
    """Return ``(token, expires_unix_ts)`` for a relative MEDIA_ROOT path."""
    ttl = int(ttl_seconds or getattr(settings, "MEDIA_URL_DEFAULT_TTL_SECONDS", 3600))
    expires = int(time.time()) + max(1, ttl)
    msg = f"{_normalize(path)}|{expires}".encode("utf-8")
    token = hmac.new(_key(), msg, hashlib.sha256).hexdigest()
    return token, expires


def verify_media_token(path: str, token: str, expires: int | str) -> bool:
    """Constant-time verification with expiry check. Never raises."""
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    if expires_int < int(time.time()):
        return False
    msg = f"{_normalize(path)}|{expires_int}".encode("utf-8")
    expected = hmac.new(_key(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(token or ""))
