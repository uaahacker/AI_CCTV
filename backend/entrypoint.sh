#!/usr/bin/env bash
# Backend container entrypoint.
# - For the "web" role: waits for DB, applies migrations, collects static, then execs CMD.
# - For "celery"/"beat" roles (chosen via the compose `command` override), just execs.
set -euo pipefail

ROLE="${ROLE:-web}"

echo "[entrypoint] starting role=${ROLE}"

# Wait for Postgres (only useful when DATABASE_URL points at the compose db).
if [[ -n "${DATABASE_URL:-}" ]]; then
    python - <<'PY'
import os, time, sys
from urllib.parse import urlparse
import socket

url = os.environ.get("DATABASE_URL", "")
u = urlparse(url)
host, port = u.hostname, u.port or 5432
if not host:
    sys.exit(0)
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[entrypoint] database reachable at {host}:{port}")
            sys.exit(0)
    except OSError:
        time.sleep(1)
print(f"[entrypoint] WARN: database {host}:{port} not reachable after 60s", flush=True)
PY
fi

if [[ "$ROLE" == "web" ]]; then
    echo "[entrypoint] generating any missing app migrations…"
    # Explicitly name every first-party app: makemigrations with no args silently
    # skips apps that lack a migrations/ package, which leaves the schema half-built
    # and breaks admin.0001_initial (FK to swappable AUTH_USER_MODEL).
    python manage.py makemigrations --noinput \
        accounts organizations cameras analytics alerts audit ai compliance
    echo "[entrypoint] running migrations…"
    python manage.py migrate --noinput
    echo "[entrypoint] collecting static files…"
    python manage.py collectstatic --noinput
fi

exec "$@"
