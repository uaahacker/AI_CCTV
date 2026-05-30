"""
Security helpers: RTSP URL encryption at rest + safe masking for API responses.

Encryption uses Fernet (symmetric). Key MUST be set via FIELD_ENCRYPTION_KEY env.
If absent in DEBUG, we fall back to storing plaintext with a warning — never do
this in production.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is not None:
        return _fernet
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not key:
        if settings.DEBUG:
            logger.warning(
                "FIELD_ENCRYPTION_KEY not set — RTSP URLs will be stored in plaintext (DEBUG only)."
            )
            return None
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set in production.")
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_str(value: str) -> str:
    if not value:
        return ""
    f = _get_fernet()
    if f is None:
        return value  # DEBUG fallback
    return f.encrypt(value.encode()).decode()


def decrypt_str(value: str) -> str:
    if not value:
        return ""
    f = _get_fernet()
    if f is None:
        return value  # DEBUG fallback
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        # Likely a legacy plaintext value from DEBUG mode.
        return value


def mask_rtsp_url(url: str) -> str:
    """Strip credentials from an RTSP URL for safe display."""
    if not url:
        return ""
    try:
        p = urlparse(url)
        if p.username or p.password:
            host = p.hostname or ""
            if p.port:
                host = f"{host}:{p.port}"
            netloc = f"***:***@{host}"
            return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
        return url
    except Exception:  # noqa: BLE001 - never break serialization on bad input
        return "***"


def validate_rtsp_url(url: str) -> bool:
    """Lightweight RTSP/HTTP(S) URL validation."""
    if not url:
        return False
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    return p.scheme in {"rtsp", "rtsps", "http", "https"} and bool(p.hostname)
