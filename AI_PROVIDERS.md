# AI Providers — How AI Works in This Project

AI in **AI CCTV Analytics** is split into **two independent layers**. Mixing them
up is a common source of confusion, so read this first.

| Layer | What it does | Where it runs | Configured by |
|---|---|---|---|
| **Computer-vision AI** | People / object detection, counting, tracking, event creation | `cv_worker/` container, on the server | Environment variables (`DETECTOR`, `YOLO_MODEL`, …) |
| **LLM / text AI** | Alert summaries, daily report insights, future chatbot | Backend (Celery task or DRF request) | Per-organization, from the dashboard |

> **The LLM never participates in detection.** Disabling AI in the dashboard
> does NOT disable people counting — that always runs in the CV worker.

---

## 1. Computer-vision AI (always-on, no configuration needed)

Implemented in `cv_worker/worker/pipeline.py`:

1. `RtspReader` (OpenCV → ffmpeg) decodes one frame at a time from the camera.
2. The active **Detector** scores that frame:
   - `DummyPeopleDetector` — sine-wave count for local dev (no model, no GPU).
   - `YOLOPeopleDetector` — Ultralytics YOLOv8, COCO class 0 = `person`.
3. The frame is **discarded immediately**. Only the integer count + confidence
   land in the database as a `DetectionEvent`.
4. The rules engine evaluates the event and may create an `Alert`.

Detectors are pluggable — add an `ObjectDetector` subclass in
`cv_worker/worker/detectors/` to support vehicles, intrusion, PPE, etc.

**You do not need an API key for CV AI.** YOLO weights are downloaded once on
first boot and cached in the container.

---

## 2. LLM / text AI (optional, per-organization)

Configured in **Settings → AI Settings** in the dashboard. Each organization
picks ONE provider type:

| `provider_type` | Default `base_url` | API key needed? |
|---|---|---|
| `disabled` | — | No (uses deterministic fallback text) |
| `openrouter` | `https://openrouter.ai/api/v1` | **Yes** — your OpenRouter key |
| `openai_compatible` | `https://api.openai.com/v1` | **Yes** — for OpenAI or any cloud-hosted compatible API |
| `local_ollama` | `http://ollama:11434/v1` | No |
| `self_hosted` | _user-supplied_ | Usually no |

All four call the OpenAI-compatible `POST /chat/completions` shape, so the
service layer is one implementation (see `backend/apps/ai/services.py`).

### Where the LLM is used

| Place | Trigger | What the LLM sees |
|---|---|---|
| `Alert.ai_summary` | Automatic, async after each alert | `title`, `severity`, `camera_name`, `message`, `metadata` (no imagery) |
| `POST /api/analytics/reports/ai-summary/` | "Generate AI summary" button on the Reports page | Aggregated counts per day/hour/camera |

If a network call fails OR the provider is `disabled`, the backend falls back
to deterministic text — the dashboard **never** crashes because the LLM is
down.

---

## 3. Safe configuration examples

### Option A — OpenRouter (cloud, easiest)

| Field | Value |
|---|---|
| Provider type | OpenRouter |
| Base URL | `https://openrouter.ai/api/v1` |
| Model name | `openrouter/auto`, `meta-llama/llama-3.1-8b-instruct`, … |
| API key | `sk-or-...` (your OpenRouter key) |

The key is encrypted at rest with the server's `FIELD_ENCRYPTION_KEY` (same
Fernet key used for RTSP URLs). It is **never** returned in API responses —
only `has_api_key` and `masked_api_key` (e.g. `sk-or-****abcd`) are.

### Option B — Local Ollama on the same server

```bash
# Start Ollama alongside the rest of the stack
docker compose --profile local-ai up -d ollama

# Pull a model into the Ollama volume (once)
docker compose exec ollama ollama pull llama3.1:8b
```

In the dashboard:

| Field | Value |
|---|---|
| Provider type | Local Ollama |
| Base URL | `http://ollama:11434/v1` |
| Model name | `llama3.1:8b` (or `qwen2.5:7b`, `mistral`, …) |
| API key | _leave blank_ |

**Important:** the compose file binds Ollama to `127.0.0.1:11434` on the host.
Never expose port `11434` publicly — Ollama has no built-in authentication.

### Option C — Self-hosted vLLM / LM Studio / text-generation-webui

Anything that exposes an OpenAI-compatible `/chat/completions` endpoint works.

| Field | Value |
|---|---|
| Provider type | Self-hosted |
| Base URL | e.g. `http://vllm:8000/v1` or `http://192.0.2.10:1234/v1` (private network) |
| Model name | whatever the runtime advertises |
| API key | usually blank, or whatever the runtime expects |

---

## 4. Security rules for AI keys

- **Never** put real API keys in `.env.example`, README, or any committed file.
- Keys live encrypted in `ai_aiprovidersetting.api_key_encrypted`.
- The serializer is `write_only` for `api_key`. The browser receives only
  `has_api_key` and `masked_api_key`.
- The frontend `AISettings.jsx` never logs the key to the console and never
  pre-fills the input.
- Only `owner` and `admin` roles can read/write AI provider settings (see
  `IsOrgAdminOrReadOnly`).
- All create/update/test actions are written to `apps.audit.AuditLog`.

---

## 5. Cost & latency notes

- Alert summaries are sized to ≤ 60 words; report summaries to ≤ 120 words.
- `max_tokens=400`, `temperature=0.2`, `HTTP_TIMEOUT_SECONDS=20` — set in
  `apps/ai/services.py`. Tune for your provider.
- Alert summaries run inside a Celery task — they never block the rules
  engine, email delivery, or the API request that triggered the event.

---

## 6. Roadmap (post-MVP)

- Chatbot/admin assistant ("how many people in the lobby right now?").
- Weekly automatic email report generated by the LLM.
- Multi-provider failover (primary + fallback model).
- Per-organization usage metering for billing.
