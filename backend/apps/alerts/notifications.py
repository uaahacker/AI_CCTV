"""
Multi-channel alert dispatcher.

Adapters are dependency-free (stdlib urllib) so adding a new channel never
forces a new pip install. Each adapter is a small callable with the signature:

    send(alert, rule, config) -> tuple[bool, str]   # (ok, detail)

Configuration is read from the AlertRule row (one row may target many
channels in parallel). Failures in one channel never break another.

Channels implemented
--------------------
- email     : Django EmailMultiAlternatives (HTML + text)
- slack     : Incoming Webhook URL (https://hooks.slack.com/services/...)
- discord   : Webhook URL (https://discord.com/api/webhooks/...)
- webhook   : Generic JSON POST to any URL (ERP / POS / alarm panel)
- sms       : Twilio REST API if TWILIO_* env vars set, else logs as no-op

Security
--------
- Full webhook URLs and Twilio credentials are NEVER logged. Only the host.
- HTTPS is required for slack/discord/webhook in production (enforced when
  DEBUG=False).
- Per-channel timeouts cap blocking time at 10 s.
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2048


# --- Helpers ---------------------------------------------------------------

def _host_only(url: str) -> str:
    """Return scheme://host for safe logging — never the secret path."""
    try:
        u = urlparse(url)
        return f"{u.scheme}://{u.netloc}"
    except Exception:  # noqa: BLE001
        return "<invalid url>"


def _require_https(url: str) -> None:
    """In production, refuse plain-http webhook destinations."""
    if not settings.DEBUG and not url.lower().startswith("https://"):
        raise ValueError("Webhook destinations must use HTTPS outside DEBUG.")


def _post_json(url: str, payload: dict, headers: dict | None = None) -> tuple[bool, str]:
    _require_https(url)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = resp.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
            return (200 <= resp.status < 300), f"{resp.status} {body[:200]}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} from {_host_only(url)}"
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def _severity_color(severity: str) -> int:
    """Discord embed colour (decimal)."""
    return {
        "critical": 0xE53E3E,  # red
        "warning":  0xDD6B20,  # orange
        "info":     0x3182CE,  # blue
    }.get(severity, 0x718096)


# --- Channel adapters ------------------------------------------------------

def send_email(alert, rule, config: dict) -> tuple[bool, str]:
    to_addr = config.get("to") or rule.notification_email
    if not to_addr:
        return False, "no email recipient configured"
    ctx = {
        "alert": alert,
        "rule": rule,
        "rule_name": rule.name,
        "camera_name": alert.camera.name if alert.camera else "",
    }
    subject = f"[AI CCTV] {alert.severity.upper()} — {alert.title}"
    text_body = render_to_string("alerts/email/alert_notification.txt", ctx)
    html_body = render_to_string("alerts/email/alert_notification.html", ctx)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_addr],
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send(fail_silently=False)
        return True, f"email queued to {to_addr}"
    except Exception as exc:  # noqa: BLE001
        return False, f"email send failed: {exc}"


def send_slack(alert, rule, config: dict) -> tuple[bool, str]:
    """POST a Slack-formatted message to an Incoming Webhook URL."""
    url = config.get("webhook_url")
    if not url:
        return False, "missing slack webhook_url"
    cam = alert.camera.name if alert.camera else "—"
    payload = {
        "text": f"*[{alert.severity.upper()}]* {alert.title}",
        "attachments": [{
            "color": {
                "critical": "#E53E3E", "warning": "#DD6B20", "info": "#3182CE",
            }.get(alert.severity, "#718096"),
            "fields": [
                {"title": "Camera",   "value": cam, "short": True},
                {"title": "Severity", "value": alert.severity, "short": True},
                {"title": "Message",  "value": alert.message[:500] or "—", "short": False},
            ],
            "footer": "AI CCTV Analytics",
            "ts": int(alert.created_at.timestamp()),
        }],
    }
    return _post_json(url, payload)


def send_discord(alert, rule, config: dict) -> tuple[bool, str]:
    """POST a Discord embed to a webhook URL."""
    url = config.get("webhook_url")
    if not url:
        return False, "missing discord webhook_url"
    cam = alert.camera.name if alert.camera else "—"
    payload = {
        "username": "AI CCTV",
        "embeds": [{
            "title": f"[{alert.severity.upper()}] {alert.title}",
            "description": (alert.message or "")[:1900],
            "color": _severity_color(alert.severity),
            "timestamp": alert.created_at.isoformat(),
            "fields": [
                {"name": "Camera",   "value": cam, "inline": True},
                {"name": "Severity", "value": alert.severity, "inline": True},
                {"name": "Rule",     "value": rule.name, "inline": False},
            ],
        }],
    }
    return _post_json(url, payload)


def send_webhook(alert, rule, config: dict) -> tuple[bool, str]:
    """Generic JSON POST. Optional HMAC-style bearer token via `auth_token`."""
    url = config.get("url")
    if not url:
        return False, "missing webhook url"
    headers = {}
    token = config.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "id": str(alert.id),
        "title": alert.title,
        "message": alert.message,
        "severity": alert.severity,
        "status": alert.status,
        "camera": {
            "id": str(alert.camera.id) if alert.camera else None,
            "name": alert.camera.name if alert.camera else None,
        },
        "rule": {"id": str(rule.id), "name": rule.name, "type": rule.rule_type},
        "metadata": alert.metadata,
        "created_at": alert.created_at.isoformat(),
    }
    return _post_json(url, payload, headers=headers)


def send_sms(alert, rule, config: dict) -> tuple[bool, str]:
    """Send SMS via Twilio if creds present, else log + no-op.

    Required env / settings: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM.
    Per-rule: config['to'] = E.164 destination.
    """
    sid   = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    sender = getattr(settings, "TWILIO_FROM", "")
    to = config.get("to")
    if not to:
        return False, "missing sms recipient"
    if not (sid and token and sender):
        logger.info("[SMS-MOCK] to=%s body=[%s] %s", to, alert.severity, alert.title)
        return True, "logged (twilio creds not configured — mock mode)"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    body = f"[{alert.severity.upper()}] {alert.title} — {alert.message[:120]}"
    data = urllib.parse.urlencode({"From": sender, "To": to, "Body": body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            return (200 <= resp.status < 300), f"twilio {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"twilio HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, f"twilio {exc.__class__.__name__}"


CHANNELS: dict[str, Callable[[Any, Any, dict], tuple[bool, str]]] = {
    "email":   send_email,
    "slack":   send_slack,
    "discord": send_discord,
    "webhook": send_webhook,
    "sms":     send_sms,
}


def dispatch(alert, rule) -> dict[str, tuple[bool, str]]:
    """Fan out alert to every enabled channel on the rule.

    Returns {channel: (ok, detail)} for logging / audit. Never raises.
    """
    results: dict[str, tuple[bool, str]] = {}
    channels = list(rule.channels or [])
    # Backward compat: legacy notification_email implies email channel.
    if rule.notification_email and "email" not in channels:
        channels.append("email")

    for ch in channels:
        adapter = CHANNELS.get(ch)
        if adapter is None:
            results[ch] = (False, "unknown channel")
            continue
        cfg = (rule.channel_config or {}).get(ch, {}) if rule.channel_config else {}
        try:
            ok, detail = adapter(alert, rule, cfg)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"{exc.__class__.__name__}: {exc}"
        results[ch] = (ok, detail)
        if ok:
            logger.info("alert=%s channel=%s OK %s", alert.id, ch, detail)
        else:
            logger.warning("alert=%s channel=%s FAIL %s", alert.id, ch, detail)
    return results
