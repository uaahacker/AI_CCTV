# Architecture

A bird's-eye view of how the AI CCTV Analytics platform is wired together.

## 1. System diagram

```
                                ┌────────────────────────┐
       IP camera                │       cv_worker        │
   (RTSP / ONVIF / NVR)  ─────► │  (one thread / camera) │
                                │                        │
                                │  OpenCV decode 1 frame │
                                │  every N seconds       │
                                │           │            │
                                │           ▼            │
                                │  apply_privacy(frame)  │  ← blur every face
                                │  (Haar cascade)        │
                                │           │            │
                                │           ▼            │
                                │  Detector.detect(frame)│  ← Dummy / YOLOv8
                                │  (returns int count +  │
                                │   confidence; frame    │
                                │   is then DISCARDED)   │
                                └───────────┬────────────┘
                                            │ ORM write
                                            ▼
                              ┌──────────────────────────┐
                              │   DetectionEvent (PG)    │
                              └────────────┬─────────────┘
                                           │ Celery .delay()
                                           ▼
                              ┌──────────────────────────┐
                              │  apps.alerts.tasks       │
                              │  evaluate_event()        │
                              │   • condition match      │
                              │   • cooldown check       │
                              │   • time-window match    │
                              │   • create Alert         │
                              └────┬──────────────┬──────┘
                                   │              │
                          deliver_alert     generate_alert_ai_summary
                                   │              │
                                   ▼              ▼
                  ┌──────────────────────┐   ┌────────────────────┐
                  │ notifications.       │   │ apps.ai.services   │
                  │   dispatch()         │   │  AIProviderFactory │
                  │  • email             │   │  • OpenRouter      │
                  │  • slack webhook     │   │  • OpenAI-compat   │
                  │  • discord webhook   │   │  • Local Ollama    │
                  │  • generic webhook   │   │  • Self-hosted     │
                  │  • twilio sms        │   │  • Disabled        │
                  └──────────────────────┘   └────────────────────┘
                                                    │
                                                    ▼
                                           Alert.ai_summary

                  Django REST API ───► React 18 + Tailwind dashboard
                  (DRF + SimpleJWT)      (axios, Recharts)
```

## 2. Processes (a runnable system)

| Process | Purpose | How it runs |
|---|---|---|
| `backend` (Django) | REST API, admin, OpenAPI docs | `gunicorn config.wsgi` (prod) / `runserver` (dev) |
| `celery_worker` | Async tasks: alerts, AI summary, daily reports | `celery -A config worker -l info` |
| `celery_beat` | Schedules: offline check (2 min), daily report (07:00) | `celery -A config beat -l info` |
| `cv_worker` | Per-camera CV pipeline, one thread per camera | `python -m worker.main` |
| `frontend` | Static React build, served by nginx | `vite build` + nginx |
| `postgres` | Source of truth | Docker image `postgres:16-alpine` |
| `redis` | Celery broker + result backend | Docker image `redis:7-alpine` |
| `nginx` (prod) | TLS termination, reverse proxy | Docker, profile `production` |
| `ollama` (optional) | Local LLM | Docker, profile `local-ai`, bound `127.0.0.1` |

## 3. Multi-tenancy model

- `Organization` is the tenant root.
- `Membership(User, Organization, role)` — roles `owner` / `admin` /
  `operator` / `viewer`.
- Every business model has an `organization` FK and every viewset filters by
  `organization__memberships__user=request.user`.
- Encrypted secrets (RTSP credentials, AI provider API keys) live on
  per-organisation rows.
- Email-based custom `User` model — see `apps.accounts`.

## 4. Data flow (one tick of one camera)

1. `CameraWorker` thread wakes up after `SAMPLE_INTERVAL_SECONDS`.
2. `RtspReader.read_one()` opens the RTSP/HTTP stream with OpenCV's
   ffmpeg-backed `VideoCapture`, decodes a single frame, returns it.
3. `CameraHealthCheck` row is written + `Camera.last_seen_at` updated. If the
   read failed the camera transitions to `OFFLINE`.
4. `apply_privacy(frame)` runs the Haar face detector and blurs every face
   in-place (GDPR default).
5. `Detector.detect(frame)` returns `(people_count, confidence, metadata)`.
6. Frame variable goes out of scope and is garbage-collected. **No video is
   written anywhere.**
7. A `DetectionEvent` row is created.
8. `evaluate_event.delay(event_id)` is enqueued.
9. Celery worker picks it up, walks active `AlertRule`s for the org,
   checks `condition` + `time-window` + `cooldown`, and may create an
   `Alert`.
10. Each new `Alert` enqueues `deliver_alert.delay(alert_id)` and
    `generate_alert_ai_summary.delay(alert_id)`.
11. `deliver_alert` fans out to every channel listed on the rule and records
    per-channel results to `Alert.delivery_log`.
12. `generate_alert_ai_summary` calls the org's configured LLM provider and
    fills `Alert.ai_summary` (no-ops safely if AI is disabled).
13. The React dashboard polls `/api/alerts/` and renders the new row, with
    its AI summary appearing a moment later.

## 5. What we **never** store

| Item | Why |
|---|---|
| Full video footage | Privacy, storage cost, legal liability. |
| Decoded frames | Discarded after the detector returns. |
| Facial features / embeddings | Faces are blurred *before* detection runs. |
| Raw RTSP credentials | Stored Fernet-encrypted; API returns masked form. |
| Raw AI API keys | Stored Fernet-encrypted; API returns masked form. |
| Customer payment data | Subscription model present as a placeholder only; integrate Stripe externally. |

`Alert.clip_path` is an opt-in 1-5 s evidence clip path for security alerts
only. The clip-writer is intentionally not part of the default deployment —
implement it (e.g. ffmpeg rolling buffer) only when your legal review approves
short-clip retention.

## 6. Storage budget (rough)

For a deployment with 50 cameras sampling every 5 seconds:

- DetectionEvent: ~864k rows/day × ~300 bytes ≈ 250 MB/day. Use Postgres
  partitioning + retention job once you exceed a few months.
- Alert: a few hundred/day at most.
- CameraHealthCheck: same volume as DetectionEvent — consider a retention
  policy of 7–30 days.

## 7. Failure modes

| Failure | Behaviour |
|---|---|
| Camera RTSP drop | `CameraHealthCheck` records error, `Camera.status` flips to `OFFLINE`, beat raises `camera_offline` alert. Worker thread retries indefinitely. |
| Postgres down | CV worker thread crashes that tick, retries next interval. Backend returns 500. |
| Redis down | Celery `.delay()` raises immediately (broker retries disabled). The dispatcher falls back to **inline** synchronous delivery so alerts still reach Slack/email. |
| LLM provider down | `BaseAIProvider._safe_chat` returns a deterministic fallback string — dashboard never shows an error. |
| Slack/Discord webhook 404 | One channel fails, others succeed; `Alert.delivery_log[<channel>] = {ok: false, detail: "..."}`. |
| Face cascade fails to load | Worker logs an error and returns the original frame; detection still runs but privacy is degraded — investigate. |

## 8. Extension points

- New CV detector → subclass `BaseDetector` (see [CV_PIPELINE.md](CV_PIPELINE.md)).
- New alert channel → add an adapter (see [NOTIFICATIONS.md](NOTIFICATIONS.md)).
- New AI provider → subclass `BaseAIProvider` (see [../AI_PROVIDERS.md](../AI_PROVIDERS.md)).
- New rule predicate → add a value to `AlertRule.RuleType` and a branch in
  `evaluate_event` or a dedicated task.
