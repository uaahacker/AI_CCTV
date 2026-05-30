# Contributing

Thanks for considering a contribution! This project welcomes issues, bug
reports, documentation fixes, and pull requests.

## Ground rules

1. **No real footage, no real credentials, no real customer data** in issues,
   PRs, screenshots, fixtures, or commits. Use the dummy detector + synthetic
   data for everything public.
2. **Privacy-by-default must stay default.** Any PR that disables face blur or
   enables facial recognition by default will be rejected.
3. **No raw-video storage.** Architectural rule — see
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §"What we never store".
4. **License compatibility.** All contributions are accepted under the project
   [MIT License](LICENSE). By opening a PR you agree to license your code
   under the same terms.

## Workflow

```bash
# 1. Fork + clone
git clone https://github.com/<you>/AI_CCTV.git
cd AI_CCTV

# 2. Branch
git checkout -b feat/your-feature

# 3. Make changes — follow conventions below
# 4. Run tests locally
docker compose exec backend python manage.py test -v 2

# 5. Commit using Conventional Commits
git commit -m "feat(alerts): add Microsoft Teams notification channel"

# 6. Push + open a PR against `main`
```

## Conventional commit prefixes

| Prefix | Meaning |
|---|---|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | No behaviour change |
| `test:` | Adding/fixing tests |
| `chore:` | Tooling / CI / dependencies |
| `perf:` | Performance change |
| `security:` | Security-related fix |

Scope (optional but appreciated): `alerts`, `cameras`, `ai`, `cv`, `frontend`, `infra`, etc.

## Code style

### Python (backend, cv_worker)
- Python 3.11+, type hints where they aid clarity (not exhaustive).
- `from __future__ import annotations` at the top of every module.
- Prefer `pathlib.Path` over `os.path` strings.
- Side-effecting imports (Django ORM access) only after `django.setup()`.
- No `print()` — use the `logging` module.
- Keep models thin; business logic in `services.py` / `tasks.py`.
- New Celery tasks go in `apps/<app>/tasks.py` and must be idempotent on
  retry.

### JavaScript / React (frontend)
- React 18 functional components only, hooks for state.
- TailwindCSS utility classes — avoid bespoke CSS files.
- Axios `api` client from `src/api.js` (handles auth + base URL).
- Never log raw API keys or RTSP URLs.

### Migrations
- One migration per logical change. Don't squash unless requested.
- Migrations must be reversible (`reverse_code` on `RunPython`).

## Adding a new alert channel

1. Add an adapter function in
   [backend/apps/alerts/notifications.py](backend/apps/alerts/notifications.py)
   with the signature `send(alert, rule, config) -> (bool, str)`.
2. Register it in the `CHANNELS` dict.
3. Add the channel name to
   `apps.alerts.models.VALID_CHANNELS`.
4. Document the expected `channel_config` keys in
   [docs/NOTIFICATIONS.md](docs/NOTIFICATIONS.md).
5. Add an opt-in env switch in `.env.example` if the channel needs API creds.
6. Add a unit test under `apps/alerts/tests.py`.

## Adding a new detector

1. Subclass `BaseDetector` in `cv_worker/worker/detectors/your_detector.py`.
2. Implement `detect(frame) -> DetectionResult`.
3. Register it in `cv_worker/worker/detectors/__init__.py`.
4. Document weights download / GPU requirements in
   [docs/CV_PIPELINE.md](docs/CV_PIPELINE.md).

## Reporting security issues

Do **not** open a public issue. Follow the process in
[SECURITY.md](SECURITY.md) §12.
