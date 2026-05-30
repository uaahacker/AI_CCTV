# Notifications & Rule Engine

Everything you need to know about getting alerts out to the right destination
at the right time.

## 1. Concepts

- **AlertRule** — a row in `apps.alerts.AlertRule`. Describes _when_ to fire
  (`rule_type`, `condition`, `threshold_value`, `active_from`/`active_to`,
  `days_of_week`), _what_ to fire on (`camera` or all cameras),
  _how often at most_ (`cooldown_seconds`), and _where_ to deliver
  (`channels`, `channel_config`).
- **Alert** — a row in `apps.alerts.Alert`. Created when a rule matches.
  Stores `severity`, `message`, `metadata`, `ai_summary`,
  `delivery_log`, and an optional `clip_path`.
- **Dispatcher** — `apps.alerts.notifications.dispatch(alert, rule)`.
  Iterates `rule.channels`, calls the adapter for each, captures
  `(ok, detail)` per channel.

## 2. Supported channels

| Channel | Adapter | Required `channel_config[<ch>]` keys | Notes |
|---|---|---|---|
| `email` | Django mail | `to` (string). Falls back to `rule.notification_email`. | HTML + text via `apps/alerts/templates/alerts/email/`. |
| `slack` | Slack Incoming Webhook | `webhook_url` (HTTPS) | Severity colour bar + structured fields. |
| `discord` | Discord Webhook | `webhook_url` (HTTPS) | Embed with colour, fields, timestamp. |
| `webhook` | Generic JSON POST | `url` (HTTPS), optional `auth_token` | Sends a typed JSON payload. |
| `sms` | Twilio REST | `to` (E.164) | Requires `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`. Mock mode if any is missing. |

### Webhook payload schema (`webhook` channel)

```json
{
  "id": "0a18…",
  "title": "Crowd threshold: 27 detected",
  "message": "Camera 'Lobby' reported 27 people (rule greater_than 20).",
  "severity": "critical",
  "status": "new",
  "camera":   { "id": "uuid", "name": "Lobby" },
  "rule":     { "id": "uuid", "name": "Peak hours", "type": "people_count" },
  "metadata": { "event_id": "uuid", "confidence": 0.91 },
  "created_at": "2026-05-30T18:12:04+00:00"
}
```

Custom HTTP header `Authorization: Bearer <auth_token>` is added when
`channel_config.webhook.auth_token` is set.

## 3. Worked example — "If people count > 20 between 18:00–20:00 → Slack #ops"

```http
POST /api/alerts/rules/
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "organization":    "<org-uuid>",
  "camera":          null,
  "name":            "Peak-hours crowding",
  "rule_type":       "people_count",
  "condition":       "greater_than",
  "threshold_value": 20,
  "active_from":     "18:00",
  "active_to":       "20:00",
  "days_of_week":    [],
  "cooldown_seconds":600,
  "channels":        ["slack", "email"],
  "channel_config":  {
    "slack": { "webhook_url": "https://hooks.slack.com/services/T000/B000/XXX" },
    "email": { "to": "ops@example.com" }
  },
  "is_active":       true
}
```

### Time-window semantics

- Empty `active_from` AND empty `active_to` → always-on.
- Window may wrap midnight: `active_from="22:00"`, `active_to="06:00"`.
- `days_of_week` uses ISO weekday integers, **1 = Monday … 7 = Sunday**.
  Empty list = every day.
- All times are compared against `timezone.localtime()` of the Django
  process (configure `TIME_ZONE` in `settings.py`).

## 4. Delivery audit

After delivery, `Alert.delivery_log` looks like:

```json
{
  "slack": { "ok": true,  "detail": "200 ok" },
  "email": { "ok": true,  "detail": "email queued to ops@example.com" },
  "sms":   { "ok": false, "detail": "twilio HTTP 401" }
}
```

The full alert (including `delivery_log`) is visible at
`GET /api/alerts/<id>/`. A failed channel does **not** block the others —
each adapter is wrapped in `try/except` inside the dispatcher.

## 5. Cooldown

`cooldown_seconds` is the minimum interval between two alerts for the same
`(rule, camera)` pair. The effective cooldown is
`max(rule.cooldown_seconds, settings.ALERT_COOLDOWN_SECONDS)` so an operator
can set a global floor.

## 6. Severity inference

The dispatcher does not pick the severity; the rules engine does (see
`apps.alerts.tasks._infer_severity`):

- `intrusion`, `abandoned_object`, `camera_offline` → `critical`
- `condition=greater_than` AND `value ≥ 2 × threshold` → `critical`
- otherwise → `warning`

Severity affects:

- Email subject prefix
- Slack attachment colour bar
- Discord embed colour

## 7. Failure & retry policy

- Celery `.delay()` is invoked with `broker_connection_retry=False`. If
  Redis is unreachable the dispatcher runs **inline synchronously** so alerts
  still reach their destinations.
- HTTP webhook timeouts: 10 s per channel.
- A future enhancement: per-channel Celery retry policy with exponential
  back-off. Not enabled by default to avoid stale alerts being delivered
  hours late.

## 8. Adding a new channel

See [CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-new-alert-channel).
A real-world example you could add in a few lines:

- **Microsoft Teams** — adapter is identical in shape to Slack/Discord; the
  webhook payload uses `MessageCard` schema.
- **PagerDuty Events API v2** — POST to
  `https://events.pagerduty.com/v2/enqueue` with a routing key.

## 9. Daily report

The Celery beat task `apps.alerts.tasks.generate_daily_reports` runs at
07:00 server-local and emits one INFO-severity Alert per organisation with
"last 24 h" totals. Because it goes through the dispatcher, the report lands
in whatever channels the org's _first active_ rule uses — typically
the same Slack channel as live alerts. Override by adding an explicit
"daily-report" rule for finer control.
