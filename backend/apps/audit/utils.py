"""Helpers for writing audit log entries."""
from __future__ import annotations

import logging
from typing import Any

from .models import AuditLog

logger = logging.getLogger(__name__)


def _client_ip(request) -> str | None:
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(
    *,
    user=None,
    action: str,
    request=None,
    organization=None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort audit logging — never raises."""
    try:
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            organization=organization,
            action=action,
            ip_address=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:300] if request else ""),
            metadata=metadata or {},
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed writing AuditLog for action=%s", action)
