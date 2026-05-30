"""
Alerts: rules engine + multi-channel delivery + camera-offline watcher.

Public Celery tasks
-------------------
- `evaluate_event(event_id)`        — eval one DetectionEvent against rules
- `check_offline_cameras()`         — beat scan for stale cameras
- `generate_alert_ai_summary(id)`   — async LLM summary for an Alert
- `deliver_alert(alert_id)`         — async multi-channel fan-out
- `generate_daily_reports()`        — beat daily, per-org analytics roll-up
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.analytics.models import DetectionEvent
from apps.cameras.models import Camera

from .models import Alert, AlertRule
from .notifications import dispatch

logger = logging.getLogger(__name__)


# --- Helpers --------------------------------------------------------------

def _condition_matches(condition: str, value: float, threshold: float) -> bool:
    if condition == AlertRule.Condition.GT:
        return value > threshold
    if condition == AlertRule.Condition.LT:
        return value < threshold
    if condition == AlertRule.Condition.EQ:
        return value == threshold
    return False


def _is_in_cooldown(rule: AlertRule, camera_id) -> bool:
    cooldown = max(rule.cooldown_seconds, settings.ALERT_COOLDOWN_SECONDS)
    since = timezone.now() - timedelta(seconds=cooldown)
    return Alert.objects.filter(
        alert_rule=rule, camera_id=camera_id, created_at__gte=since
    ).exists()


def _parse_hhmm(value: str) -> time | None:
    try:
        h, m = value.split(":")
        return time(hour=int(h), minute=int(m))
    except (ValueError, AttributeError):
        return None


def _in_time_window(rule: AlertRule, now: datetime | None = None) -> bool:
    """Check the rule's active_from/active_to/days_of_week predicate.

    Empty start/end means always-on. Window may wrap midnight (e.g. 22:00-06:00).
    `days_of_week` empty list means every day; otherwise list of 1=Mon..7=Sun.
    """
    now = now or timezone.localtime()
    if rule.days_of_week:
        if now.isoweekday() not in rule.days_of_week:
            return False
    if not rule.active_from and not rule.active_to:
        return True
    start = _parse_hhmm(rule.active_from) or time(0, 0)
    end = _parse_hhmm(rule.active_to) or time(23, 59, 59)
    t = now.time()
    if start <= end:
        return start <= t <= end
    # Wraps midnight.
    return t >= start or t <= end


def _infer_severity(rule: AlertRule, value: float) -> str:
    if rule.rule_type in {
        AlertRule.RuleType.CAMERA_OFFLINE,
        AlertRule.RuleType.INTRUSION,
        AlertRule.RuleType.ABANDONED_OBJECT,
    }:
        return Alert.Severity.CRITICAL
    if rule.condition == AlertRule.Condition.GT and value >= rule.threshold_value * 2:
        return Alert.Severity.CRITICAL
    return Alert.Severity.WARNING


def _create_alert(*, rule: AlertRule, camera, organization, title: str, message: str,
                  value: float, metadata: dict) -> Alert:
    severity = _infer_severity(rule, value)
    # Lift the evidence-clip path out of the metadata so it's directly
    # queryable from the Alerts admin / API (clip_path is a top-level field).
    clip_path = ""
    if isinstance(metadata, dict):
        clip_path = str(metadata.get("clip_path") or "")
    alert = Alert.objects.create(
        organization=organization,
        camera=camera,
        alert_rule=rule,
        title=title,
        message=message,
        severity=severity,
        metadata=metadata,
        clip_path=clip_path,
    )
    # Multi-channel delivery off the request thread.
    try:
        deliver_alert.delay(str(alert.id))
    except Exception:  # noqa: BLE001
        logger.warning("Could not enqueue deliver_alert for %s; running inline", alert.id)
        deliver_alert(str(alert.id))
    # LLM summary (best-effort, async).
    try:
        generate_alert_ai_summary.delay(str(alert.id))
    except Exception:  # noqa: BLE001
        logger.warning("Could not enqueue AI summary for alert %s", alert.id)
    return alert


# --- Tasks ---------------------------------------------------------------

@shared_task
def deliver_alert(alert_id: str) -> dict:
    """Fan out one Alert to every configured channel on its rule."""
    try:
        alert = Alert.objects.select_related("alert_rule", "camera", "organization").get(id=alert_id)
    except Alert.DoesNotExist:
        return {}
    rule = alert.alert_rule
    if not rule:
        return {}
    results = dispatch(alert, rule)
    log = {ch: {"ok": ok, "detail": detail} for ch, (ok, detail) in results.items()}
    Alert.objects.filter(id=alert.id).update(delivery_log=log)
    return log


@shared_task
def generate_alert_ai_summary(alert_id: str) -> bool:
    """Populate Alert.ai_summary using the org's configured AI provider."""
    from apps.ai.services import AIProviderFactory

    try:
        alert = Alert.objects.select_related("organization", "camera").get(id=alert_id)
    except Alert.DoesNotExist:
        return False
    provider = AIProviderFactory.for_organization(alert.organization)
    summary = provider.generate_alert_summary({
        "title": alert.title,
        "severity": alert.severity,
        "camera_name": alert.camera.name if alert.camera else None,
        "message": alert.message,
        "metadata": alert.metadata,
    })
    if summary:
        Alert.objects.filter(id=alert.id).update(ai_summary=summary)
    return bool(summary)


@shared_task
def evaluate_event(event_id: str) -> int:
    """Evaluate a single DetectionEvent against active AlertRules."""
    try:
        event = DetectionEvent.objects.select_related("camera", "organization").get(id=event_id)
    except DetectionEvent.DoesNotExist:
        return 0

    rules = AlertRule.objects.filter(
        organization=event.organization,
        is_active=True,
        rule_type__in=[
            AlertRule.RuleType.PEOPLE_COUNT,
            AlertRule.RuleType.CROWD,
            event.event_type,
        ],
    )

    created = 0
    for rule in rules:
        if rule.camera_id and rule.camera_id != event.camera_id:
            continue
        if not _in_time_window(rule):
            continue
        if not _condition_matches(rule.condition, event.people_count, rule.threshold_value):
            continue
        if _is_in_cooldown(rule, event.camera_id):
            continue

        _create_alert(
            rule=rule,
            camera=event.camera,
            organization=event.organization,
            title=f"{rule.name}: {event.people_count} detected",
            message=(
                f"Camera '{event.camera.name}' reported {event.people_count} people "
                f"(rule {rule.condition} {rule.threshold_value})."
            ),
            value=event.people_count,
            metadata={"event_id": str(event.id), "confidence": event.confidence},
        )
        created += 1
    return created


@shared_task
def check_offline_cameras(max_age_minutes: int = 5) -> int:
    """Scan all active CAMERA_OFFLINE rules and raise alerts for stale cameras."""
    cutoff = timezone.now() - timedelta(minutes=max_age_minutes)
    rules = AlertRule.objects.filter(
        is_active=True, rule_type=AlertRule.RuleType.CAMERA_OFFLINE
    ).select_related("organization")

    created = 0
    for rule in rules:
        cameras_qs = Camera.objects.filter(organization=rule.organization, is_active=True)
        if rule.camera_id:
            cameras_qs = cameras_qs.filter(id=rule.camera_id)
        for cam in cameras_qs:
            is_stale = (cam.last_seen_at is None) or (cam.last_seen_at < cutoff)
            is_bad_status = cam.status in {Camera.Status.OFFLINE, Camera.Status.ERROR}
            if not (is_stale or is_bad_status):
                continue
            if _is_in_cooldown(rule, cam.id):
                continue
            _create_alert(
                rule=rule,
                camera=cam,
                organization=rule.organization,
                title=f"Camera offline: {cam.name}",
                message=(
                    f"Camera '{cam.name}' has not reported since "
                    f"{cam.last_seen_at or 'never'} (status={cam.status})."
                ),
                value=1,
                metadata={
                    "last_seen_at": cam.last_seen_at.isoformat() if cam.last_seen_at else None,
                    "status": cam.status,
                },
            )
            created += 1
    return created


@shared_task
def generate_daily_reports() -> int:
    """Beat-daily roll-up: emit one INFO alert per org with the last-24h summary.

    The alert flows through the same multi-channel dispatcher, so each org's
    rule can choose where the daily digest goes (Slack #ops, email, etc.).
    Only orgs that have a rule with rule_type=people_count AND is_active are
    considered (acts as opt-in).
    """
    from apps.organizations.models import Organization
    from apps.analytics.models import DetectionEvent as DE

    since = timezone.now() - timedelta(days=1)
    emitted = 0
    for org in Organization.objects.all():
        rule = AlertRule.objects.filter(
            organization=org, is_active=True
        ).order_by("created_at").first()
        if not rule:
            continue
        events = DE.objects.filter(organization=org, created_at__gte=since)
        total = events.count()
        peak = events.order_by("-people_count").values_list("people_count", flat=True).first() or 0
        _create_alert(
            rule=rule,
            camera=None,
            organization=org,
            title=f"Daily report — {total} detections, peak {peak}",
            message=(
                f"Last 24h: {total} detection events across all cameras. "
                f"Peak headcount: {peak}."
            ),
            value=0,
            metadata={"kind": "daily_report", "total": total, "peak": peak},
        )
        emitted += 1
    return emitted
