# Installation guide

Three install paths, easiest first.

| Path | Best for | Time |
|---|---|---|
| [One-line installer](#1-one-line-installer-recommended) | VPS / home server / quick demo | ~5 min |
| [Manual Docker](#2-manual-docker) | You want to inspect every step | ~10 min |
| [Local dev (no Docker)](#3-local-development-without-docker) | Contributors / hacking on the code | ~15 min |

> **Public-repo reminder** — never commit `.env`, real RTSP URLs, real API
> keys, or TLS certs. The installer marks `.env` as `chmod 600`, but it is
> still your responsibility to keep it out of git. See [SECURITY.md](SECURITY.md).

---

## 1. One-line installer (recommended)

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/UbaidUllah/AI_CCTV/main/install.sh | bash
```

### Windows (Docker Desktop must be running)

```powershell
iwr -useb https://raw.githubusercontent.com/UbaidUllah/AI_CCTV/main/install.ps1 | iex
```

### What it does

1. **Verifies Docker** — installs Docker Engine + Compose plugin via
   `get.docker.com` on Linux if missing. On Windows it expects Docker Desktop
   to already be installed and running.
2. **Clones the repo** to `/opt/ai-cctv` (Linux) or `%USERPROFILE%\AI_CCTV`
   (Windows). Pulls the latest commit on re-run.
3. **Runs the first-time wizard**, asking for:
   - public hostname or IP (auto-detected)
   - whether to enable HTTPS (you supply the certs)
   - admin email + password (becomes Django superuser — leave password blank
     to auto-generate)
   - optional AI provider + API key (OpenRouter / OpenAI / Ollama / custom)
   - optional SMTP credentials for email alerts
4. **Generates strong secrets** — `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`
   (Fernet), `POSTGRES_PASSWORD`.
5. **Writes `.env`** (chmod 600), `docker compose build`, `docker compose up -d`.
6. **Waits for the backend**, runs `migrate`, creates the superuser
   idempotently.
7. **Prints the dashboard URL and admin password** — copy the password now,
   it is hashed in the DB and not recoverable.

### Re-running, flags, and unattended mode

Both installers are safe to re-run — they update the checkout and re-apply
migrations without overwriting `.env`.

| Need | Bash flag | PowerShell flag |
|---|---|---|
| Overwrite `.env` and re-run the wizard | `--reconfigure` | `-Reconfigure` |
| Skip the wizard entirely (CI / scripts) | `--noninteractive` | `-NonInteractive` |
| Install to a different directory | `--dir=/srv/cctv` | `-InstallDir D:\cctv` |
| Different repo or branch | `--repo=… --branch=…` | `-RepoUrl … -Branch …` |

For unattended runs, set these env vars before invoking the script:

```bash
export NONINTERACTIVE=1
export PUBLIC_HOST=cctv.example.com
export ADMIN_EMAIL=you@example.com
export ADMIN_PASSWORD='whatever-you-want'   # optional — auto-generated if absent
curl -fsSL https://raw.githubusercontent.com/UbaidUllah/AI_CCTV/main/install.sh | bash
```

### After install

```bash
cd /opt/ai-cctv
docker compose ps                                    # status
docker compose logs -f backend cv_worker celery_worker
docker compose pull && docker compose up -d          # update to latest
docker compose down                                  # stop
```

Open `http://<your-host>` and log in with the admin credentials.

---

## 2. Manual Docker

If you prefer to drive each step:

```bash
git clone https://github.com/UbaidUllah/AI_CCTV.git
cd AI_CCTV
cp .env.example .env

# Generate the three secrets and paste them into .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
python3 -c "from cryptography.fernet import Fernet; print('FIELD_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"

docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

For production TLS termination via the bundled nginx profile, see
[DEPLOYMENT.md](DEPLOYMENT.md).

---

## 3. Local development without Docker

You need: Python 3.11+, Node 18+, Redis, PostgreSQL (or SQLite for quick tests).

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp ../.env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Celery (in two more terminals — needs Redis)
celery -A config worker -l info
celery -A config beat   -l info

# Frontend
cd ../frontend && npm install && npm run dev          # http://localhost:5173

# CV worker
cd ../cv_worker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m worker.main
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full env-var
reference and [CONTRIBUTING.md](CONTRIBUTING.md) for the dev workflow.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `permission denied` on `/var/run/docker.sock` | Log out and back in after the installer adds you to the `docker` group, or run with `sudo`. |
| Installer hangs at "Waiting for backend" | `docker compose logs backend` — usually a bad `DATABASE_URL` or missing `FIELD_ENCRYPTION_KEY`. |
| Forgot the admin password | `docker compose exec backend python manage.py changepassword you@example.com` |
| Want to wipe everything and start over | `cd <install dir> && docker compose down -v && rm .env && ./install.sh --reconfigure` |
| Hostname / IP changed | Edit `.env` (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_BASE_URL`) and `docker compose up -d` to reload. |

For anything not covered here, open a discussion on the GitHub repo or
email the maintainer (see [SECURITY.md](SECURITY.md) §12 for the address).
