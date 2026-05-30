# Data Model

Reference of the persistent entities. Field names match the Django models;
types are abbreviated.

> Every model inherits from `apps.common.models.TimeStampedModel`, which
> provides a UUID `id` primary key plus `created_at` / `updated_at`.

## accounts

### `User` (custom, email-based)
| Field | Type |
|---|---|
| email | Email (unique, used as login) |
| first_name, last_name | str |
| is_active, is_staff, is_superuser | bool |
| date_joined | datetime |

## organizations

### `Organization`
| Field | Type |
|---|---|
| name | str |
| slug | str (unique) |

### `Membership`
| Field | Type |
|---|---|
| user | FK → User |
| organization | FK → Organization (related_name `memberships`) |
| role | enum `owner` / `admin` / `operator` / `viewer` |

## cameras

### `Camera`
| Field | Type |
|---|---|
| organization | FK → Organization |
| name | str |
| location | str |
| rtsp_url_encrypted | text (Fernet) |
| rtsp_url | property — encrypts on set, decrypts on get |
| rtsp_url_masked | property — for API responses |
| status | enum `online`/`offline`/`error`/`unknown` |
| last_seen_at | datetime nullable |
| last_error | text |
| is_active | bool |

### `CameraHealthCheck`
| Field | Type |
|---|---|
| camera | FK → Camera |
| status | enum (same as above) |
| latency_ms | int |
| error_message | text |

## analytics

### `DetectionEvent`
| Field | Type |
|---|---|
| organization | FK → Organization |
| camera | FK → Camera |
| event_type | enum (`people_count`, `intrusion`, `crowd_threshold`) |
| people_count | int |
| confidence | float |
| metadata | JSON |

Indexes: `(organization, -created_at)`, `(camera, -created_at)`, `event_type`.

## alerts

### `AlertRule`
| Field | Type |
|---|---|
| organization | FK → Organization |
| camera | FK → Camera nullable (null = all cameras in org) |
| name | str |
| rule_type | enum — see below |
| condition | enum `greater_than` / `less_than` / `equals` |
| threshold_value | float |
| is_active | bool |
| cooldown_seconds | int |
| notification_email | email (legacy single recipient) |
| channels | JSON list — `["email","slack","discord","webhook","sms"]` |
| channel_config | JSON — per-channel config |
| active_from | str `"HH:MM"` |
| active_to | str `"HH:MM"` |
| days_of_week | JSON list of ISO weekday ints |

`rule_type` enum:

```
people_count, crowd_threshold, queue_length, dwell_time,
intrusion, line_crossing, loitering, abandoned_object,
parking_occupied, parking_illegal, parking_duration,
camera_offline
```

### `Alert`
| Field | Type |
|---|---|
| organization | FK |
| camera | FK nullable |
| alert_rule | FK nullable |
| title | str |
| message | text |
| severity | enum `info`/`warning`/`critical` |
| status | enum `new`/`acknowledged`/`resolved` |
| metadata | JSON |
| ai_summary | text — LLM-generated, async |
| clip_path | str — relative to MEDIA_ROOT (optional) |
| clip_duration_s | int (0-5 typical) |
| delivery_log | JSON — `{channel: {ok, detail}}` |

## ai

### `AIProviderSetting`
One per organisation (OneToOne).

| Field | Type |
|---|---|
| organization | OneToOne → Organization |
| provider_type | enum `disabled`/`openrouter`/`openai_compatible`/`local_ollama`/`self_hosted` |
| display_name | str |
| base_url | URL |
| model_name | str |
| api_key_encrypted | text (Fernet) |
| api_key | write-only property |
| masked_api_key | property — `sk-or-****abcd` |
| has_api_key | property — bool |
| is_active | bool |

## audit

### `AuditLog`
| Field | Type |
|---|---|
| user | FK → User nullable |
| organization | FK → Organization nullable |
| action | str |
| target_repr | str |
| ip_address | IP nullable |
| metadata | JSON |

## billing

### `SubscriptionPlan`
| Field | Type |
|---|---|
| name | str |
| price_cents | int |
| max_cameras | int |
| features | JSON |

### `OrganizationSubscription`
| Field | Type |
|---|---|
| organization | OneToOne → Organization |
| plan | FK → SubscriptionPlan |
| status | enum `active`/`past_due`/`canceled`/`trialing` |
| current_period_end | datetime |

## compliance

### `DataProcessingConsent`
| Field | Type |
|---|---|
| organization | FK → Organization |
| accepted_by | FK → User |
| written_consent | bool |
| camera_ownership | bool |
| data_processing_terms | bool |
| terms_version | str |
| ip_address | IP nullable |
| user_agent | str |
| notes | text |
| revoked_at | datetime nullable |
| is_valid | property |

## Cardinality at a glance

```
User ─┬─ Membership ──→ Organization ─┬─ Camera ──→ DetectionEvent
      │                               │           └─ CameraHealthCheck
      │                               ├─ AlertRule ──→ Alert
      │                               ├─ AIProviderSetting (1)
      │                               ├─ DataProcessingConsent (n)
      │                               ├─ OrganizationSubscription (1)
      │                               └─ AuditLog (n)
      └─ AuditLog (n)
```


## New models (enterprise hardening)

### apps.cameras.Recording

Promoted hourly MP4 file produced by `apps.cameras.recording_tasks.promote_recordings`
for cameras whose `recording_policy` is `continuous`.

- `camera`        FK -> apps.cameras.Camera
- `kind`          CharField  (continuous | motion | clip)
- `started_at`    DateTimeField (UTC, top of hour)
- `ended_at`      DateTimeField
- `duration_s`    PositiveInteger
- `size_bytes`    PositiveBigInteger
- `file_path`     CharField(500), relative to MEDIA_ROOT

Served via signed URLs through `/api/media/file/` (see ARCHITECTURE.md).
Purged after `RECORDING_RETENTION_DAYS`.

### apps.alerts.AlertDelivery

One row per channel attempt for a given alert. See NOTIFICATIONS.md.

### apps.accounts.PasswordResetToken / EmailVerificationToken

Single-use tokens, `token_hash` stored as `sha256(token).hexdigest()`
so a DB leak cannot impersonate the user. TTL: 1 hour (reset) / 2 days
(verify).

## New / changed fields

- `Organization.retention_days`  PositiveInteger (default `DEFAULT_RETENTION_DAYS`)
- `Organization.deleted_at`      DateTimeField (null, db_index) - soft-delete sentinel
- `Camera.recording_policy`      CharField (off | continuous | motion)
- `User.email_verified`          BooleanField (default False)
