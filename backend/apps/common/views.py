"""Operations endpoints: health probe, Prometheus metrics, signed media URLs.

These intentionally live in ``apps.common`` so they don't pull in any
domain-specific imports at module load time \u2014 the health endpoint must keep
working even when one app is misconfigured.
"""
from __future__ import annotations

import mimetypes
import os

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .signing import sign_media_path, verify_media_token


# --- Health probe --------------------------------------------------------

def _check_db() -> tuple[bool, str]:
    from django.db import connections
    try:
        with connections["default"].cursor() as c:
            c.execute("SELECT 1")
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, exc.__class__.__name__


def _check_redis() -> tuple[bool, str]:
    url = getattr(settings, "CELERY_BROKER_URL", "") or getattr(settings, "REDIS_URL", "")
    if not url:
        return False, "no broker configured"
    try:
        import redis  # type: ignore
        client = redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=1.5)
        return bool(client.ping()), "ok"
    except Exception as exc:  # noqa: BLE001
        return False, exc.__class__.__name__


def _check_celery() -> tuple[bool, str, int]:
    """Best-effort ping \u2014 doesn't fail health if Celery is offline.

    Returns ``(ok, detail, worker_count)``.
    """
    try:
        from celery import current_app  # type: ignore
        insp = current_app.control.inspect(timeout=1.0)
        stats = insp.stats() or {}
        return True, "ok", len(stats)
    except Exception as exc:  # noqa: BLE001
        return False, exc.__class__.__name__, 0


class HealthView(APIView):
    """``GET /api/health/`` \u2014 liveness + dependency probes.

    Returns 200 even when optional dependencies (celery, redis) are down so
    that the public ELB keeps the web pod in rotation; the JSON body lets
    monitoring tools alert on the individual checks.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []  # never enforce auth on health

    def get(self, request):
        db_ok, db_detail = _check_db()
        redis_ok, redis_detail = _check_redis()
        celery_ok, celery_detail, celery_workers = _check_celery()
        body = {
            "status": "ok" if db_ok else "degraded",
            "time": timezone.now().isoformat(),
            "version": getattr(settings, "RELEASE_VERSION", "dev"),
            "checks": {
                "database": {"ok": db_ok, "detail": db_detail},
                "redis":    {"ok": redis_ok, "detail": redis_detail},
                "celery":   {"ok": celery_ok, "detail": celery_detail,
                             "workers": celery_workers},
            },
        }
        http_status = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(body, status=http_status)


# --- Prometheus metrics --------------------------------------------------

class MetricsView(APIView):
    """``GET /api/health/metrics/`` \u2014 Prometheus text exposition format.

    Gated by ``settings.PROMETHEUS_METRICS_ENABLED``. Exposes a tiny set of
    business gauges in addition to the default process collectors that the
    SDK registers automatically. Add more metrics here as needed.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []

    def get(self, request):
        if not getattr(settings, "PROMETHEUS_METRICS_ENABLED", True):
            return HttpResponse(status=404)
        try:
            from prometheus_client import (  # type: ignore
                CONTENT_TYPE_LATEST, generate_latest, REGISTRY, Gauge,
            )
        except ImportError:
            return HttpResponse("prometheus_client not installed",
                                status=500, content_type="text/plain")

        # Lazily create gauges so the test suite can reload the module
        # without a "duplicate timeseries" error.
        if not hasattr(MetricsView, "_gauges"):
            MetricsView._gauges = {
                "cameras_total": Gauge("aicctv_cameras_total", "Cameras in the fleet"),
                "cameras_online": Gauge("aicctv_cameras_online", "Cameras currently online"),
                "alerts_open": Gauge("aicctv_alerts_open", "Open alerts across all orgs"),
                "deliveries_failed_24h": Gauge(
                    "aicctv_deliveries_failed_24h",
                    "Alert deliveries that failed in the last 24h",
                ),
            }
        g = MetricsView._gauges
        try:
            from datetime import timedelta
            from apps.alerts.models import Alert, AlertDelivery
            from apps.cameras.models import Camera
            g["cameras_total"].set(Camera.objects.count())
            g["cameras_online"].set(Camera.objects.filter(status="online").count())
            g["alerts_open"].set(Alert.objects.filter(status="new").count())
            since = timezone.now() - timedelta(hours=24)
            g["deliveries_failed_24h"].set(
                AlertDelivery.objects.filter(
                    status="failed", created_at__gte=since
                ).count()
            )
        except Exception:  # noqa: BLE001 \u2014 never break metrics scraping
            pass

        return HttpResponse(generate_latest(REGISTRY), content_type=CONTENT_TYPE_LATEST)


# --- Signed media access -------------------------------------------------

class MediaSignURLView(APIView):
    """``POST /api/media/sign/`` body: ``{path, ttl?}`` \u2192 signed query string.

    The caller must be authenticated and must own the media object (we
    enforce ownership on the *paths* by allow-listing a prefix per
    organisation: hls/<camera_id>/..., recordings/<camera_id>/..., clips/...).
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "media_sign"

    def post(self, request):
        path = (request.data.get("path") or "").strip().lstrip("/")
        ttl = int(request.data.get("ttl") or 0) or None
        if not path:
            return Response({"detail": "path is required"}, status=400)
        if not _user_can_read_path(request.user, path):
            return Response({"detail": "not allowed"}, status=403)
        token, expires = sign_media_path(path, ttl_seconds=ttl)
        return Response({
            "path": path,
            "url": f"/api/media/file/?path={path}&token={token}&expires={expires}",
            "token": token,
            "expires": expires,
        })


class MediaFileView(APIView):
    """``GET /api/media/file/?path=&token=&expires=`` \u2014 stream a media file.

    Auth is by HMAC token, NOT JWT, so ``<video>`` tags can play HLS without
    custom headers.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []

    def get(self, request):
        path = (request.query_params.get("path") or "").strip().lstrip("/")
        token = request.query_params.get("token") or ""
        expires = request.query_params.get("expires") or "0"
        if not path or not verify_media_token(path, token, expires):
            return HttpResponse(status=403)

        full_path = os.path.normpath(os.path.join(str(settings.MEDIA_ROOT), path))
        media_root = os.path.normpath(str(settings.MEDIA_ROOT))
        # Defence: stop path traversal even though sign_media_path normalises it.
        if not full_path.startswith(media_root + os.sep) and full_path != media_root:
            return HttpResponse(status=403)
        if not os.path.isfile(full_path):
            return HttpResponse(status=404)

        ctype, _ = mimetypes.guess_type(full_path)
        # HLS playlists need a precise content type so hls.js doesn't choke.
        if full_path.endswith(".m3u8"):
            ctype = "application/vnd.apple.mpegurl"
        elif full_path.endswith(".ts"):
            ctype = "video/mp2t"
        resp = FileResponse(open(full_path, "rb"), content_type=ctype or "application/octet-stream")
        # Playlists must NEVER be cached \u2014 they update every couple seconds.
        if full_path.endswith(".m3u8"):
            resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
        else:
            resp["Cache-Control"] = "private, max-age=60"
        return resp


def _user_can_read_path(user, path: str) -> bool:
    """Authorise ``path`` (relative to MEDIA_ROOT) for ``user``.

    Allowed prefixes are ``hls/<camera_id>/``, ``recordings/<camera_id>/``,
    ``clips/<camera_id>/`` where ``<camera_id>`` belongs to one of the
    user's organisations. Other prefixes are denied by default.
    """
    parts = path.split("/")
    if len(parts) < 2:
        return False
    bucket, camera_id = parts[0], parts[1]
    if bucket not in {"hls", "recordings", "clips"}:
        return False
    from apps.cameras.models import Camera
    return Camera.objects.filter(
        id=camera_id, organization__memberships__user=user
    ).exists()
