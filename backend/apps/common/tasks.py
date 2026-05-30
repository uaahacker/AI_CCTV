"""Cross-cutting Celery tasks: retention purge, hard-delete of orgs.

Both tasks are idempotent — re-running them only deletes rows that meet the
respective age threshold. Wired into the beat schedule in ``config.celery``.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)


def _safe_unlink(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.unlink(path)
    except OSError:
        log.warning("retention: failed to unlink %s", path, exc_info=True)


def _safe_rmtree(path: str) -> None:
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        log.warning("retention: failed to remove tree %s", path, exc_info=True)


@shared_task(name="common.purge_expired_data")
def purge_expired_data() -> dict:
    """Delete data older than each organisation's ``retention_days``.

    Runs daily (see ``CELERY_BEAT_SCHEDULE``). Touches:
      * DetectionEvent / HeatmapBucket / Alert / AlertDelivery (per-org TTL)
      * AuditLog (uses ``AUDIT_RETENTION_DAYS`` regardless of org TTL)
      * Evidence clip files referenced by purged Alerts
      * Recording rows + files older than ``RECORDING_RETENTION_DAYS``

    Returns a small JSON-able summary for the Celery result backend.
    """
    from apps.alerts.models import Alert, AlertDelivery
    from apps.analytics.models import DetectionEvent, HeatmapBucket
    from apps.audit.models import AuditLog
    from apps.organizations.models import Organization

    summary: dict[str, int] = {
        "alerts": 0, "deliveries": 0, "events": 0, "heatmaps": 0,
        "audit_logs": 0, "recordings": 0, "clip_files": 0,
    }

    now = timezone.now()

    for org in Organization.objects.all():
        ttl = max(1, int(org.retention_days or settings.DEFAULT_RETENTION_DAYS))
        cutoff = now - timedelta(days=ttl)

        # Delete clip files referenced by alerts we're about to purge.
        media_root = str(settings.MEDIA_ROOT)
        for alert in Alert.objects.filter(organization=org, created_at__lt=cutoff).only("clip_path"):
            if alert.clip_path:
                _safe_unlink(os.path.join(media_root, alert.clip_path))
                summary["clip_files"] += 1

        # AlertDelivery cascades from Alert but is cheaper to bulk-delete first.
        d_count, _ = AlertDelivery.objects.filter(
            alert__organization=org, created_at__lt=cutoff
        ).delete()
        summary["deliveries"] += d_count

        a_count, _ = Alert.objects.filter(organization=org, created_at__lt=cutoff).delete()
        summary["alerts"] += a_count

        e_count, _ = DetectionEvent.objects.filter(
            organization=org, created_at__lt=cutoff
        ).delete()
        summary["events"] += e_count

        h_count, _ = HeatmapBucket.objects.filter(
            camera__organization=org, hour_bucket__lt=cutoff
        ).delete()
        summary["heatmaps"] += h_count

    audit_cutoff = now - timedelta(
        days=max(1, int(getattr(settings, "AUDIT_RETENTION_DAYS", 365)))
    )
    al_count, _ = AuditLog.objects.filter(created_at__lt=audit_cutoff).delete()
    summary["audit_logs"] += al_count

    # Recordings (continuous CCTV) — gated by RECORDING_RETENTION_DAYS.
    try:
        from apps.cameras.models import Recording
    except ImportError:  # pragma: no cover — migrations may not be applied yet
        Recording = None  # type: ignore
    if Recording is not None:
        rec_ttl = int(getattr(settings, "RECORDING_RETENTION_DAYS", 7) or 0)
        if rec_ttl > 0:
            rec_cutoff = now - timedelta(days=rec_ttl)
            old = Recording.objects.filter(started_at__lt=rec_cutoff)
            for r in old.only("file_path"):
                if r.file_path:
                    _safe_unlink(os.path.join(str(settings.MEDIA_ROOT), r.file_path))
            r_count, _ = old.delete()
            summary["recordings"] += r_count

    log.info("retention purge: %s", summary)
    return summary


@shared_task(name="common.purge_deleted_organizations")
def purge_deleted_organizations(grace_days: int = 7) -> dict:
    """Hard-delete organisations that requested deletion ``grace_days`` ago.

    Until the grace period expires the org is hidden from the UI (see
    ``Organization.objects`` default queryset) but recoverable by support.
    """
    from apps.organizations.models import Organization

    cutoff = timezone.now() - timedelta(days=max(1, int(grace_days)))
    qs = Organization.all_objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
    media_root = str(settings.MEDIA_ROOT)

    purged: list[str] = []
    for org in qs:
        # Wipe HLS + recording directories for each camera in this org.
        for cam_id in org.cameras.values_list("id", flat=True):
            _safe_rmtree(os.path.join(media_root, "hls", str(cam_id)))
            _safe_rmtree(os.path.join(media_root, "recordings", str(cam_id)))
            _safe_rmtree(os.path.join(media_root, "clips", str(cam_id)))
        purged.append(str(org.id))
        org.delete()  # cascades through every related model

    log.info("hard-deleted orgs: %s", purged)
    return {"organizations": len(purged), "ids": purged}
