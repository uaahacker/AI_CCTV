# Configuration Reference

Every environment variable understood by the stack, grouped by component.

> Defaults shown in parentheses. Variables marked **required-in-prod** must
> be set when `DEBUG=False`.

## 1. Core Django

| Var | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `dev-insecure-change-me` | **required-in-prod**. Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. |
| `DEBUG` | `True` | Set `False` outside local dev. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated. |
| `CORS_ALLOWED_ORIGINS` | empty | Comma-separated exact origins. |
| `TIME_ZONE` | `UTC` | Affects rule `active_from/active_to` semantics. |

## 2. Database & cache

| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | empty (uses SQLite) | e.g. `postgres://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://localhost:6379/1` | Used by Django cache & Celery. |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | Set `True` to run tasks synchronously (tests). |

## 3. Encryption

| Var | Default | Notes |
|---|---|---|
| `FIELD_ENCRYPTION_KEY` | empty | **required-in-prod**. Fernet key used to encrypt RTSP URLs AND AI API keys. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Back this up offline — losing it makes encrypted columns unreadable. |

## 4. Email

| Var | Default | Notes |
|---|---|---|
| `EMAIL_BACKEND` | console backend | e.g. `django.core.mail.backends.smtp.EmailBackend` |
| `DEFAULT_FROM_EMAIL` | `alerts@aicctv.local` | |
| `EMAIL_HOST` | empty | |
| `EMAIL_PORT` | `587` | |
| `EMAIL_HOST_USER` | empty | |
| `EMAIL_HOST_PASSWORD` | empty | Prefer app-passwords. |
| `EMAIL_USE_TLS` | `True` | |

## 5. SMS / Twilio (optional)

| Var | Default | Notes |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | empty | When any of the three is empty the SMS adapter runs in mock mode (logs only, never sends). |
| `TWILIO_AUTH_TOKEN` | empty | |
| `TWILIO_FROM` | empty | E.164 sender, e.g. `+15551234567`. |

## 6. Privacy & compliance

| Var | Default | Notes |
|---|---|---|
| `PRIVACY_BLUR_FACES` | `True` | Set `False` only with documented legal basis. |
| `PRIVACY_FACIAL_RECOGNITION_ENABLED` | `False` | No FR pipeline ships with the project; this flag merely controls whether the warning fires. |
| `CONSENT_TERMS_VERSION` | `1.0` | Bump when terms text changes. |

## 7. Alerting

| Var | Default | Notes |
|---|---|---|
| `ALERT_COOLDOWN_SECONDS` | `300` | Global minimum cooldown; effective cooldown = `max(rule.cooldown_seconds, this)`. |

## 8. CV worker

| Var | Default | Notes |
|---|---|---|
| `DETECTOR` | `dummy` | `dummy` or `yolo`. |
| `YOLO_MODEL` | `yolov8n.pt` | Used only when `DETECTOR=yolo`. |
| `YOLO_CONF` | `0.35` | Confidence threshold. |
| `SAMPLE_INTERVAL_SECONDS` | `5` | Per-camera sample period. |
| `CAMERA_REFRESH_SECONDS` | `30` | Supervisor refresh. |
| `RTSP_READ_TIMEOUT_SECONDS` | `10` | Open-stream timeout. |
| `RECONNECT_BACKOFF_SECONDS` | `5` | Wait after exceptions. |

## 9. Frontend (Vite)

| Var | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Set absolute origin when frontend and API are on different hosts. |
| `FRONTEND_PORT` | `80` | Docker host port for nginx. |

## 10. AI (LLM)

LLM API keys are **not** environment variables. They are stored encrypted
per-organisation in `apps.ai.AIProviderSetting`. See
[AI_PROVIDERS.md](../AI_PROVIDERS.md).

## 11. Production hardening (auto when `DEBUG=False`)

`settings.py` automatically enables:

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
```

Place `nginx` (or equivalent TLS terminator) in front of `gunicorn`.

## 12. Generating production secrets — one-liner

```powershell
@"
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(64))')
FIELD_ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
POSTGRES_PASSWORD=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
"@ | Out-File -Encoding ascii .env.secrets
```

Then copy/paste those three lines into your real `.env`.
