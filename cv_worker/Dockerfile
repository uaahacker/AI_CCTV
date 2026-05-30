# CV worker — runs alongside backend, shares its Django ORM.
# Build context MUST be the repo root (see docker-compose.yml) so both
# `cv_worker/` and `backend/` are accessible to COPY.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BACKEND_PATH=/backend \
    DJANGO_SETTINGS_MODULE=config.settings

# OpenCV (headless) needs libGL/libglib at runtime even for the headless wheel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libpq5 libgl1 libglib2.0-0 ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /worker

# 1) Worker code + deps
COPY cv_worker/requirements.txt /worker/requirements.txt
RUN pip install -r /worker/requirements.txt

COPY cv_worker/ /worker/

# 2) Backend code (mounted at /backend, added to PYTHONPATH by worker.settings)
COPY backend/ /backend/

RUN useradd --create-home --shell /bin/bash app \
 && chown -R app:app /worker /backend
USER app

CMD ["python", "-m", "worker.main"]
