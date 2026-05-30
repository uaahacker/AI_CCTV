# AI CCTV Analytics

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![Django 5](https://img.shields.io/badge/django-5.x-092E20.svg)](https://www.djangoproject.com)
[![React 18](https://img.shields.io/badge/react-18.x-61DAFB.svg)](https://react.dev)
[![Code of Conduct](https://img.shields.io/badge/Code%20of%20Conduct-Contributor%20Covenant%202.1-purple.svg)](CODE_OF_CONDUCT.md)

> **Open-source, self-hostable, multi-tenant SaaS** that turns existing
> IP/CCTV cameras into a real-time people-counting, crowd-alerting,
> camera-health dashboard with optional LLM-generated insights. **Privacy by
> default** — face blur on, facial recognition off, no raw video stored.

> ⚠ **Public-repo warning** — never commit `.env`, real RTSP URLs, real API
> keys, real database passwords, or TLS certs. See [SECURITY.md](SECURITY.md).

---

## Highlights

- 🎥 **CV pipeline** — OpenCV + pluggable detectors (Dummy / YOLOv8); per-camera worker threads.
- 🛡 **Privacy-first** — every face is blurred before the detector sees the frame. No raw footage is persisted.
- 🔔 **Smart triggers** — IF-THIS-THEN-THAT rule engine with time-window predicates and **5 notification channels**: Email, Slack, Discord, generic Webhook, SMS (Twilio).
- 🧠 **Optional LLM insights** — per-organisation provider (OpenRouter, OpenAI-compatible, Local Ollama, self-hosted). Disabling LLM never disables detection.
- 📊 **Reports & dashboards** — daily/hourly trends, per-camera breakdown, AI-generated daily summary on demand.
- 🔐 **Multi-tenant RBAC** — `owner` / `admin` / `operator` / `viewer` per organisation.
- 🧾 **Compliance** — `DataProcessingConsent` records written consent, camera ownership, and data-processing terms with full provenance.
- 📜 **Audit log** — every sensitive action recorded with user, IP, metadata.
- 🐳 **Docker-native** — one-command bring-up; optional production nginx profile; optional `local-ai` profile bundles Ollama bound to `127.0.0.1`.

## Tech stack

| Layer | Stack |
|---|---|
| Backend | Django 5 · DRF · SimpleJWT · Celery · Redis · PostgreSQL |
| Frontend | React 18 · Vite · TailwindCSS · Recharts · Axios |
| CV worker | Python · OpenCV (ffmpeg) · Dummy / YOLOv8 |
| AI / LLM | OpenAI-compatible: OpenRouter, OpenAI, Ollama, vLLM, LM Studio, … |
| Infra | Docker · docker-compose · nginx · WhiteNoise · Let's Encrypt |

## Architecture (one paragraph)

`cv_worker` opens each camera's RTSP stream with OpenCV, decodes one frame every N seconds, blurs every detected face (`apply_privacy`), passes the anonymised frame to the active detector, persists a `DetectionEvent`, then drops the frame. The Django backend runs Celery tasks that evaluate detection events against the organisation's active rules, raise `Alert`s, and fan them out via the multi-channel dispatcher (Email + Slack + Discord + Webhook + SMS). An optional LLM provider writes a one-paragraph human summary into `Alert.ai_summary` asynchronously. The React dashboard renders cameras, alerts, reports, and lets admins configure rules, AI providers, and consent.

Full diagram: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation

| Topic | Doc |
|---|---|
| Start here | [docs/README.md](docs/README.md) |
| Install (3 paths) | [INSTALL.md](INSTALL.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Data model | [docs/DATA_MODEL.md](docs/DATA_MODEL.md) |
| CV pipeline | [docs/CV_PIPELINE.md](docs/CV_PIPELINE.md) |
| REST API | [docs/API.md](docs/API.md) |
| Configuration | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| Notifications & rules | [docs/NOTIFICATIONS.md](docs/NOTIFICATIONS.md) |
| Privacy | [docs/PRIVACY.md](docs/PRIVACY.md) |
| Compliance (GDPR) | [docs/COMPLIANCE.md](docs/COMPLIANCE.md) |
| AI providers | [AI_PROVIDERS.md](AI_PROVIDERS.md) |
| Security policy | [SECURITY.md](SECURITY.md) |
| Deployment (EC2) | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Code of conduct | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

## Project layout

```
backend/    Django project (config + 9 apps: accounts, organizations,
            cameras, analytics, alerts, billing, audit, ai, compliance)
frontend/   React + Vite SPA
cv_worker/  Standalone OpenCV worker (shares Django ORM, runs as its own process)
infra/      nginx config for the production reverse-proxy
docs/       Module deep-dives — see docs/README.md for the index
LICENSE, README.md, SECURITY.md, DEPLOYMENT.md, AI_PROVIDERS.md,
CONTRIBUTING.md, CODE_OF_CONDUCT.md, CHANGELOG.md,
docker-compose.yml, Makefile, .env.example, .gitignore
```

## One-line install (recommended)

Got a Linux VPS or a Mac/Linux box with Docker? Run this and follow the
prompts — it installs Docker if missing, clones the repo, generates all
secrets, asks for admin/AI/SMTP details, starts the stack, applies
migrations, and creates your superuser:

```bash
curl -fsSL https://raw.githubusercontent.com/UbaidUllah/AI_CCTV/main/install.sh | bash
```

Windows (Docker Desktop installed and running):

```powershell
iwr -useb https://raw.githubusercontent.com/UbaidUllah/AI_CCTV/main/install.ps1 | iex
```

When it finishes you'll see the public URL, admin email, and a generated
admin password (saved nowhere — copy it now). Re-run with `--reconfigure`
(bash) or `-Reconfigure` (PowerShell) to regenerate `.env`. Full reference
including unattended/CI flags: [INSTALL.md](INSTALL.md).

## Manual Docker quick start

Prefer to drive it yourself? The installer is just a convenience wrapper
around these steps:

```powershell
git clone https://github.com/UbaidUllah/AI_CCTV.git
cd AI_CCTV
Copy-Item .env.example .env

# Generate real secrets — paste these into .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print('FIELD_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
# Update DATABASE_URL in .env with the same POSTGRES_PASSWORD

docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

Open **http://localhost** — register, create an organisation, record consent at *Settings → Compliance*, add a camera, configure notification channels per rule, and optionally configure AI in *Settings → AI Settings*.

```powershell
docker compose logs -f backend celery_worker cv_worker         # tail logs
docker compose exec backend python manage.py seed_detections --count 100
docker compose exec backend python manage.py test -v 2          # run tests
docker compose down                                              # stop
docker compose down -v                                           # stop + wipe DB
```

For production TLS termination:

```powershell
docker compose --profile production up -d
```

Optional bundled local LLM (Ollama, bound to `127.0.0.1:11434`):

```powershell
docker compose --profile local-ai up -d ollama
docker compose exec ollama ollama pull llama3.1:8b
# Then in the dashboard: Settings → AI Settings → Local Ollama
```

Full server walkthrough: [DEPLOYMENT.md](DEPLOYMENT.md).

## Local dev without Docker

```powershell
# Backend
cd backend
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Celery (needs Redis running)
celery -A config worker -l info
celery -A config beat   -l info

# Frontend
cd ..\frontend ; npm install ; npm run dev   # http://localhost:5173

# CV worker (uses dummy detector by default)
cd ..\cv_worker
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m worker.main
```

## Smart triggers & notifications

The rule engine evaluates every `DetectionEvent` against active `AlertRule`s.
A rule encodes: **which** event type, **what** condition + threshold, **when**
(time window + days of week), **how often at most** (cooldown), and **where**
to deliver (any combination of the 5 channels below).

| Channel | Required config |
|---|---|
| `email` | `channel_config.email.to` or `notification_email` |
| `slack` | `channel_config.slack.webhook_url` |
| `discord` | `channel_config.discord.webhook_url` |
| `webhook` | `channel_config.webhook.url` (+ optional `auth_token`) |
| `sms` | `channel_config.sms.to` + Twilio env vars (else mock-mode) |

Worked examples, payload schemas, severity inference, and the delivery audit
trail: [docs/NOTIFICATIONS.md](docs/NOTIFICATIONS.md).

## Privacy & compliance at a glance

- Face blur is **on by default** — Haar cascade runs before any detector sees the frame.
- Facial recognition is **off by default**, with no FR pipeline shipped.
- Raw video is **never stored**. Only aggregate metadata.
- Per-organisation `DataProcessingConsent` records written consent + camera ownership + data-processing terms with IP / user-agent / terms-version provenance.
- All RTSP URLs and AI API keys are Fernet-encrypted at rest.

Full details: [docs/PRIVACY.md](docs/PRIVACY.md), [docs/COMPLIANCE.md](docs/COMPLIANCE.md), [SECURITY.md](SECURITY.md).

## API documentation

Live OpenAPI 3 schema served from a running instance:

| URL | Format |
|---|---|
| `/api/schema/` | Raw YAML |
| `/api/docs/` | Interactive Swagger UI |
| `/api/redoc/` | ReDoc reference |

Higher-level guide: [docs/API.md](docs/API.md).

## Roadmap

- [x] Multi-tenant Django backend, React dashboard, OpenCV worker (Dummy + YOLOv8)
- [x] Rules engine with cooldown + offline-camera watcher
- [x] Dockerised stack with TLS profile
- [x] AI provider abstraction (OpenRouter / OpenAI-compat / Ollama / self-hosted)
- [x] Multi-channel notifications: Email + Slack + Discord + Webhook + SMS
- [x] Time-window predicates on rules
- [x] Privacy face-blur default + `DataProcessingConsent`
- [x] Open-source release (MIT)
- [ ] Object tracking (entry/exit, line-crossing, loitering, abandoned object)
- [ ] Parking zones (slot occupancy, illegal parking, duration)
- [ ] Heatmaps + queue-length detector
- [ ] ONVIF auto-discovery
- [ ] Evidence-clip writer (rolling ffmpeg buffer, ≤5 s)
- [ ] Rate limiting on auth, JWT blacklist, MFA, Stripe billing

## Contributing

PRs, issues, and documentation fixes are very welcome. Please read:

- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow & code style
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards
- [SECURITY.md](SECURITY.md) — responsible disclosure (do **not** open public issues for vulnerabilities)

## License & author

Released under the **MIT License** — see [LICENSE](LICENSE). Free for personal, commercial, and SaaS use; attribution required.

Created and maintained by **Ubaid Ullah** — software engineer. Reach me at
[ubaidawan244@gmail.com](mailto:ubaidawan244@gmail.com) for collaboration,
responsible-disclosure reports (see [SECURITY.md](SECURITY.md) §12), or just
to say hi.

**Deployer's note** — this software performs video analytics on real-world camera footage. Compliance with local laws (GDPR, CCPA, biometrics regulations) is your responsibility as the deployer. The MIT licence disclaims all warranties.
