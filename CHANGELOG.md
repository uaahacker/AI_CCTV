# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Live HLS preview**: new `streamer` compose service spawns one ffmpeg
  per active camera, writing rolling HLS chunks to `MEDIA_ROOT/hls/<id>/`.
  Frontend nginx serves them at `/media/hls/<id>/index.m3u8`; new
  `LiveFeed` React component (hls.js) embeds the player on the dashboard
  and per-camera detail page. Tunable via `STREAMER_REFRESH_SECONDS` and
  `STREAMER_REENCODE=1` (for H.265 cameras).
- **Counters API**: `GET /api/analytics/counters/?camera=&hours=24` returns
  rolling totals for people in/out, vehicles in/out, loitering,
  abandoned objects, and a parking summary. Backed by a new
  `CountersWidget` shown on the dashboard and per-camera page.
- `line_crossing` events now include the object's YOLO `label` in
  `metadata`, enabling people-vs-vehicle counter splits.

### Removed
- **Billing app**: `apps.billing` deleted along with the Stripe adapter,
  `/api/billing/*` URLs, `stripe_webhook` throttle, `STRIPE_*` settings,
  the `stripe` Python dependency, and the `/billing` page + sidebar entry
  in the dashboard. **Upgrade note**: before pulling, run
  `docker compose exec backend python manage.py migrate billing zero` to
  drop the `billing_*` Postgres tables.


- **Parking analytics**: `Zone.kind=parking_slot` slots produce live
  `ParkingSlotState` rows (FREE / OCCUPIED / ILLEGAL) and emit
  `parking_occupied`, `parking_vacated`, `parking_illegal`,
  `parking_duration` events. New endpoint `GET /api/analytics/parking/`.
- **Heatmaps**: 16×16 grid `HeatmapBucket` writer in the worker plus
  `GET /api/analytics/heatmap/?camera=&hours=` returning a normalised grid
  for dashboard rendering.
- **ONVIF auto-discovery**: stdlib-only WS-Discovery probe plus optional
  TCP/554 subnet scan, exposed at `POST /api/cameras/discover/`.
- **Evidence-clip writer**: in-memory `RollingClipBuffer` (≤
  `EVIDENCE_CLIP_SECONDS`, default 5 s) flushed to
  `MEDIA_ROOT/clips/<camera>/<event>.mp4` on alertable events. Clip path
  is auto-attached to the generated `Alert`.
- **Auth hardening**: DRF scoped throttles for login/register/refresh/MFA,
  JWT refresh-token blacklist on logout (`POST /api/auth/logout/`), and
  **TOTP MFA** (`/api/auth/mfa/enroll`, `confirm`, `status`, `disable`,
  `verify`) with two-step login (`mfa_token` challenge).
- **Stripe billing**: optional `apps.billing.stripe_adapter` (only loaded
  when `STRIPE_SECRET_KEY` is set). New checkout / portal actions on the
  subscription endpoint and signature-verified webhook at
  `POST /api/billing/webhook/`.

### Changed
- `install.sh` / `install.ps1` now run `makemigrations` before `migrate`
  so first-boot creates any pending app migrations automatically.

## [Unreleased Previous]

### Added
- **One-line installer** for VPS / Docker hosts:
  `install.sh` (bash, Linux/macOS) and `install.ps1` (PowerShell, Windows).
  Detects/installs Docker, clones the repo, runs an interactive wizard for
  admin credentials + AI keys + SMTP, auto-generates `SECRET_KEY` /
  `FIELD_ENCRYPTION_KEY` / `POSTGRES_PASSWORD`, brings the stack up, applies
  migrations, and creates the Django superuser. See [INSTALL.md](INSTALL.md).
- Multi-channel notification dispatcher with adapters for **Email, Slack,
  Discord, generic Webhook, and SMS (Twilio)** — see
  [docs/NOTIFICATIONS.md](docs/NOTIFICATIONS.md).
- `AlertRule` time-window predicate (`active_from`, `active_to`,
  `days_of_week`) — enables "IF count > 20 between 18:00–20:00" rules
  natively.
- `Alert.delivery_log` JSON field — per-channel success/failure recorded for
  audit.
- `Alert.clip_path` + `clip_duration_s` fields for 1–5 s evidence clips
  (architecture preserves "no full-footage storage").
- 8 new `AlertRule.RuleType` enum values: `queue_length`, `dwell_time`,
  `line_crossing`, `loitering`, `abandoned_object`, `parking_occupied`,
  `parking_illegal`, `parking_duration`.
- New Django app **`apps.compliance`** with `DataProcessingConsent` model and
  REST endpoint at `POST /api/compliance/consents/` — captures written
  consent, camera ownership, and data-processing-terms acceptance with IP /
  user-agent / terms-version provenance.
- CV worker **face-blur preprocessing** (`cv_worker/worker/privacy.py`) using
  OpenCV's bundled Haar cascade; runs **before** any detector sees the frame.
- `PRIVACY_BLUR_FACES` (default `True`) and
  `PRIVACY_FACIAL_RECOGNITION_ENABLED` (default `False`) env switches.
- `generate_daily_reports` Celery beat task — emits a daily INFO alert per
  organisation, routed through the multi-channel dispatcher.
- AI provider abstraction (`apps.ai`) supporting OpenRouter, OpenAI-compatible
  endpoints, Local Ollama, and self-hosted backends.
- Public-repo safety hardening: stricter `.gitignore`, placeholder-only
  `.env.example`, [SECURITY.md](SECURITY.md), [DEPLOYMENT.md](DEPLOYMENT.md),
  [AI_PROVIDERS.md](AI_PROVIDERS.md), [LICENSE](LICENSE),
  [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Optional Docker Compose `local-ai` profile that runs Ollama bound to
  `127.0.0.1:11434`.

### Changed
- `evaluate_event` now consults the rule's time-window predicate.
- `_create_alert` enqueues `deliver_alert` Celery task; falls back to inline
  delivery if the broker is unreachable.
- Celery `broker_connection_retry*` set to `False` — request threads fail
  fast instead of blocking on Redis retries.

### Security
- Webhook URLs and Twilio credentials are never logged in full — only
  `scheme://host`.
- HTTPS is enforced on Slack/Discord/generic webhook destinations when
  `DEBUG=False`.

## [0.6.0] — Initial MVP

### Added
- Django 5 + DRF backend with apps: `accounts`, `organizations`, `cameras`,
  `analytics`, `alerts`, `billing`, `audit`.
- React 18 + Vite + Tailwind dashboard with auth, cameras, alerts, reports,
  organizations pages.
- `cv_worker` standalone OpenCV process with pluggable Dummy / YOLOv8
  detectors.
- Rules engine with cooldown + offline-camera watcher + email alerts.
- Postgres + Redis + Celery + Celery Beat stack.
- Encrypted RTSP URLs via Fernet (`apps.common.security`).
- Dockerised stack with nginx production profile.
- OpenAPI 3 schema + Swagger UI + ReDoc.
- Test suites for `alerts`, `cameras`, `accounts`.

[Unreleased]: https://github.com/<you>/AI_CCTV/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/<you>/AI_CCTV/releases/tag/v0.6.0
