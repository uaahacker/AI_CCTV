# Security Policy & Checklist

> Audience: anyone running an instance of **AI CCTV Analytics** in production.
> The dashboard handles real camera credentials and customer footage metadata,
> so treat this checklist as mandatory before going live.

## 1. Public-repo safety checklist

Before pushing to a public GitHub repository:

- [ ] `.env` is not tracked. Only `.env.example` is committed.
- [ ] No real `SECRET_KEY`, database password, SMTP password, AI API key, or
      Stripe/AWS credential appears anywhere in the tree.
- [ ] No real RTSP URL with embedded credentials (`rtsp://user:pass@…`).
- [ ] No production hostnames, private IPs, or internal subdomains in code or
      docs (test fixtures may use `10.0.0.1` — RFC 1918 documentation only).
- [ ] `db.sqlite3`, `*.log`, `media/`, `staticfiles/`, `node_modules/`,
      `dist/`, `__pycache__/`, `*.pem`, `*.key`, `*.pt` (weights) are ignored.
- [ ] `infra/nginx/certs/` is ignored (only `.gitkeep` is committed).
- [ ] `git log -p` has been spot-checked for previously committed secrets. If
      anything leaked historically, **rotate it AND scrub history** (with
      `git filter-repo` or `bfg`), then force-push.

A pre-commit safety net:

```bash
pip install pre-commit detect-secrets
detect-secrets scan > .secrets.baseline
```

## 2. No raw video stored, by design

The CV worker (`cv_worker/`) opens RTSP, decodes one frame at a time, runs
detection, and **discards the frame**. Only aggregate metadata is persisted:

| Stored | Not stored |
|---|---|
| `DetectionEvent.people_count`, `confidence`, `timestamp` | Raw video, decoded frames, snapshots |
| `Alert.title`, `message`, `severity`, `ai_summary` | Bounding boxes, face crops |
| `CameraHealthCheck` status / latency | Per-frame imagery |

If you add snapshot/clip storage later, add explicit retention policies + a
customer-visible opt-in.

## 3. RTSP credential handling

- RTSP URLs are stored encrypted in `cameras.rtsp_url_encrypted` using Fernet
  (`apps/common/security.py`).
- The encryption key is `FIELD_ENCRYPTION_KEY` from the environment — same key
  used for AI provider API keys.
- API responses return `rtsp_url_masked` only (e.g. `rtsp://***:***@10.0.0.1/`).
- The plaintext is only ever materialised inside the backend or CV worker
  process, in memory.

## 4. AI provider API key handling

- Encrypted at rest with the same Fernet key.
- `write_only` in the serializer — never returned in API responses.
- The frontend never pre-fills the input and never logs it to console.
- Only `owner` / `admin` roles can create / update AI provider settings.
- Every change is recorded in `apps.audit.AuditLog`.

See [AI_PROVIDERS.md](AI_PROVIDERS.md) for the full design.

## 5. RBAC & tenant isolation

Per-organization roles: `owner`, `admin`, `operator`, `viewer`.

- All viewsets filter by `organization__memberships__user=request.user`
  (verified in `apps/cameras/tests.py` and `apps/ai/tests.py`).
- Writes restricted with `IsOrgAdminOrReadOnly`.
- Cross-tenant access returns `404`, not `403`, to avoid leaking existence.

## 6. Audit logging

`apps.audit.utils.log_action(...)` is called on every sensitive mutation:
register, camera create/update/delete, alert rule create/update, AI provider
create/update/test. Each entry records user, organization, action, IP, and
JSON metadata.

## 7. Authentication & sessions

- Email-based custom user model (`accounts.User`).
- JWT via `djangorestframework-simplejwt` — 60 min access, 7 d refresh,
  `ROTATE_REFRESH_TOKENS=True`.
- Recommended: enable `BLACKLIST_AFTER_ROTATION=True` and add
  `rest_framework_simplejwt.token_blacklist` for stricter logout semantics.

## 8. Rate limiting (TODO)

Not enabled in the MVP. Add for production:

- nginx `limit_req_zone` in front of `/api/auth/token/` and
  `/api/auth/register/`, OR
- `django-ratelimit` decorators on those views.

## 9. Secret management

- `SECRET_KEY` — generate per environment, store in your secret manager.
  Rotating it invalidates every existing JWT.
- `FIELD_ENCRYPTION_KEY` — back up offline. Losing it makes every encrypted
  RTSP URL and every encrypted AI API key unrecoverable.
- Database password — unique per environment, ≥ 24 chars, generated.
- SMTP password — use an app-password or a service account with no other
  privileges.

## 10. Transport & network

When `DEBUG=False`, Django enables: `SECURE_SSL_REDIRECT`,
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS (30 d, with subdomains
+ preload), `X_FRAME_OPTIONS=DENY`, `SECURE_PROXY_SSL_HEADER`. See
`backend/config/settings.py`.

Network expectations:

- Public: `80`, `443` only.
- Private (Docker network or VPC SG): `5432` Postgres, `6379` Redis,
  `8000` Django, `11434` Ollama.
- SSH: restricted to your office/VPN IP.

## 11. Dependency hygiene

```bash
# Backend
docker compose exec backend pip list --outdated
docker compose exec backend pip-audit            # add to CI

# Frontend
cd frontend && npm audit --omit=dev
```

Add a CI job that fails on high/critical advisories.

## 12. Responsible disclosure

Found a vulnerability? Please do **not** open a public GitHub issue. Email the
maintainer at `ubaidawan244@gmail.com`. Allow 90 days for a fix before public disclosure.

PGP key fingerprint, contact form, or a `SECURITY.txt` at the deployment
domain should be added here.

## 13. Known gaps (tracked for post-MVP)

- No rate limiting on auth endpoints.
- No JWT blacklist app enabled.
- No `pip-audit` / `npm audit` in CI.
- No MFA.
- No tenant-level data-export endpoint (GDPR Art. 20).
- No content moderation on LLM outputs.
