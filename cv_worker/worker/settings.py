"""
Bootstrap Django so the worker can use the same ORM, models and Celery app
as the backend. This module MUST be imported before any `apps.*` import.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent.parent
load_dotenv(HERE / ".env")

BACKEND_PATH = (HERE / os.environ.get("BACKEND_PATH", "../backend")).resolve()
if not BACKEND_PATH.exists():
    raise RuntimeError(
        f"BACKEND_PATH does not exist: {BACKEND_PATH}. "
        "Set BACKEND_PATH in cv_worker/.env to point at the backend/ folder."
    )

sys.path.insert(0, str(BACKEND_PATH))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()


# ---- Worker config (read after Django is set up) -----------------------
def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DETECTOR = os.environ.get("DETECTOR", "dummy").lower()
SAMPLE_INTERVAL_SECONDS = _int("SAMPLE_INTERVAL_SECONDS", 5)
CAMERA_REFRESH_SECONDS = _int("CAMERA_REFRESH_SECONDS", 30)
RTSP_READ_TIMEOUT_SECONDS = _int("RTSP_READ_TIMEOUT_SECONDS", 10)
RECONNECT_BACKOFF_SECONDS = _int("RECONNECT_BACKOFF_SECONDS", 15)
MAX_CAMERAS = _int("MAX_CAMERAS", 64)
DUMMY_MAX_PEOPLE = _int("DUMMY_MAX_PEOPLE", 15)
YOLO_MODEL = os.environ.get("YOLO_MODEL", "yolov8n.pt")
YOLO_CONF = float(os.environ.get("YOLO_CONF", "0.35"))

# --- Phase 5: tracking + evidence clips -------------------------------------
ENABLE_TRACKING = os.environ.get("ENABLE_TRACKING", "1") != "0"
EVIDENCE_CLIPS_ENABLED = os.environ.get("EVIDENCE_CLIPS_ENABLED", "1") != "0"
EVIDENCE_CLIP_SECONDS = _int("EVIDENCE_CLIP_SECONDS", 5)
HEATMAP_FLUSH_EVERY_TICKS = _int("HEATMAP_FLUSH_EVERY_TICKS", 12)

