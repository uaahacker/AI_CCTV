# API Reference

> The canonical API reference is the live OpenAPI 3 schema:
>
> | URL | Format |
> |---|---|
> | `/api/schema/` | Raw YAML |
> | `/api/docs/` | Interactive Swagger UI |
> | `/api/redoc/` | ReDoc reference |
>
> This document is a higher-level guide.

## 1. Versioning & base path

All endpoints live under `/api/` (no version prefix in the URL — the project
follows a "v1-by-omission, breaking changes require a `/api/v2/` mount"
policy).

Authentication: JSON Web Tokens (SimpleJWT).

```
Authorization: Bearer <access_token>
```

## 2. Authentication

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/auth/register/` | `{email, password, first_name?, last_name?}` | `{id, email, …}` + 201 |
| POST | `/api/auth/token/` | `{email, password}` | `{access, refresh}` |
| POST | `/api/auth/token/refresh/` | `{refresh}` | `{access}` |
| GET  | `/api/auth/me/` | — | current user payload |

## 3. Resources (CRUD)

All resources are scoped by the requesting user's `organization` memberships.

| Resource | Path | Notes |
|---|---|---|
| Organizations | `/api/organizations/organizations/` | Owners & admins manage members. |
| Memberships | `/api/organizations/memberships/` | `(user, organization, role)`. |
| Cameras | `/api/cameras/cameras/` | `rtsp_url` is write-only; response carries `rtsp_url_masked`. |
| Camera health | `/api/cameras/health/` | Read-only. |
| Detection events | `/api/analytics/events/` | Read-only, filterable by camera/date. |
| Reports | `/api/analytics/reports/?days=7&camera=<uuid>` | Aggregated daily + hourly. |
| Reports — AI summary | `POST /api/analytics/reports/ai-summary/?days=7` | LLM rollup. |
| Alert rules | `/api/alerts/rules/` | See [NOTIFICATIONS.md](NOTIFICATIONS.md). |
| Alerts | `/api/alerts/alerts/` | Read + PATCH for `status`. |
| Subscription plans | `/api/billing/plans/` | Read-only catalogue. |
| Org subscription | `/api/billing/subscriptions/` | One per org. |
| Audit log | `/api/audit/logs/` | Read-only, owner+admin. |
| AI provider | `/api/ai/providers/` | API key write-only. |
| AI test connection | `POST /api/ai/providers/<id>/test-connection/` | Synchronous probe. |
| Consent | `/api/compliance/consents/` | Create + read; immutable. |

## 4. Standard pagination

DRF page-number pagination: `?page=2&page_size=25`. Default `page_size=25`,
max 100.

```json
{
  "count": 137,
  "next":  "https://…?page=3",
  "previous": "https://…?page=1",
  "results": [ … ]
}
```

## 5. Filtering & ordering

Most list endpoints support `django-filter` query parameters. Common ones:

| Endpoint | Filter examples |
|---|---|
| `/api/analytics/events/` | `?camera=<uuid>&created_at__gte=2026-05-01` |
| `/api/alerts/alerts/` | `?status=new&severity=critical&camera=<uuid>` |
| `/api/cameras/cameras/` | `?status=online&organization=<uuid>` |

Ordering: `?ordering=-created_at`.

## 6. Permissions matrix

| Role | Create org | Manage members | Add camera | Edit AI key | Create rule | Ack alert | View audit |
|---|---|---|---|---|---|---|---|
| `owner` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `admin` | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `operator` | — | — | — | — | — | ✅ | — |
| `viewer` | — | — | — | — | — | — | — |

Enforced by `IsOrgAdminOrReadOnly` and per-view `get_queryset` filters.

## 7. Error format

DRF default. Validation errors:

```json
{ "field_name": ["Error message."] }
```

Non-field / generic:

```json
{ "detail": "Authentication credentials were not provided." }
```

## 8. Rate limiting

Not enabled in the default settings. Recommended for production:

- nginx `limit_req_zone` on `/api/auth/token/` and `/api/auth/register/`.
- Or `django-ratelimit` decorator on the same endpoints.

## 9. CORS

Configure exact frontend origins via `CORS_ALLOWED_ORIGINS` (comma-separated).
Never use `*` in production.

## 10. Webhooks emitted by us

When `channel=webhook` is configured on an `AlertRule`, the system POSTs a
JSON body to your URL. Schema is documented in
[NOTIFICATIONS.md](NOTIFICATIONS.md) §2.

## 11. Examples

```bash
# Acquire token
curl -X POST https://your.host/api/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"…"}'

# List active cameras
curl https://your.host/api/cameras/cameras/?status=online \
  -H "Authorization: Bearer $ACCESS"

# Create an after-hours intrusion rule
curl -X POST https://your.host/api/alerts/rules/ \
  -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' \
  -d '{
    "organization": "…",
    "name": "After-hours intrusion",
    "rule_type": "intrusion",
    "condition": "greater_than",
    "threshold_value": 0,
    "active_from": "20:00",
    "active_to":   "06:00",
    "channels":    ["slack","email"],
    "channel_config": {
      "slack": {"webhook_url":"https://hooks.slack.com/services/T/B/X"},
      "email": {"to":"oncall@example.com"}
    }
  }'
```
