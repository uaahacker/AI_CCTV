# Backend Django + Celery image (also reused by the cv_worker via shared code copy).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps:
#   libpq5      → psycopg runtime
#   build-essential / libpq-dev → only during pip install (then removed)
#   curl        → for healthcheck
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libpq5 curl build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
 && apt-get purge -y --auto-remove build-essential libpq-dev

COPY . .

# Non-root user
RUN useradd --create-home --shell /bin/bash app \
 && mkdir -p /app/staticfiles /app/media \
 && chown -R app:app /app
USER app

COPY --chown=app:app entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
