"""Camera health / RTSP connectivity tasks (placeholders for Phase 3)."""
from __future__ import annotations

import logging
import socket
from urllib.parse import urlparse

from celery import shared_task
from django.utils import timezone

from .models import Camera, CameraHealthCheck

logger = logging.getLogger(__name__)


def _tcp_probe(host: str, port: int, timeout: float = 3.0) -> tuple[bool, int | None, str]:
    """Lightweight TCP connect probe. Real RTSP handshake comes in Phase 3."""
    start = timezone.now()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = int((timezone.now() - start).total_seconds() * 1000)
            return True, latency, ""
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)


@shared_task
def check_camera_health(camera_id: str) -> str:
    """Probe a camera's RTSP endpoint and record a CameraHealthCheck."""
    try:
        cam = Camera.objects.get(id=camera_id)
    except Camera.DoesNotExist:
        return "missing"

    url = cam.rtsp_url
    try:
        p = urlparse(url)
        host = p.hostname or ""
        port = p.port or (554 if p.scheme.startswith("rtsp") else 80)
    except Exception as exc:  # noqa: BLE001
        cam.status = Camera.Status.ERROR
        cam.last_error = f"Bad URL: {exc}"
        cam.save(update_fields=["status", "last_error", "updated_at"])
        return "bad_url"

    if not host:
        cam.status = Camera.Status.ERROR
        cam.last_error = "Missing host"
        cam.save(update_fields=["status", "last_error", "updated_at"])
        return "bad_url"

    ok, latency, err = _tcp_probe(host, port)
    status = Camera.Status.ONLINE if ok else Camera.Status.OFFLINE
    CameraHealthCheck.objects.create(
        camera=cam, status=status, latency_ms=latency, error_message=err
    )
    cam.status = status
    cam.last_error = err
    if ok:
        cam.last_seen_at = timezone.now()
    cam.save(update_fields=["status", "last_error", "last_seen_at", "updated_at"])
    return status
