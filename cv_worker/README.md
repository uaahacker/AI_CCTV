# CV Worker

Standalone OpenCV-based detection worker that:

1. Reads active cameras from Postgres (via the Django ORM shared with `backend/`).
2. Opens each RTSP stream in a dedicated thread.
3. Runs a pluggable detector (`DummyPeopleDetector` by default, `YOLOPeopleDetector` stub ready).
4. Writes `DetectionEvent` rows — **metadata only, never the video frames**.
5. Updates `CameraHealthCheck` + `Camera.status` / `last_seen_at`.
6. Triggers the Phase-4 rules engine via Celery (`alerts.tasks.evaluate_event`).

## Quick start

From the repo root:

```powershell
cd cv_worker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# .env should point DJANGO_SETTINGS_MODULE at the backend and share the same
# DATABASE_URL, FIELD_ENCRYPTION_KEY and CELERY_BROKER_URL as backend/.env.

python -m worker.main
```

To switch detectors set `DETECTOR=yolo` in `.env` and install `ultralytics`.

## Privacy

Frames are processed in-memory and discarded. No image is written to disk by
default. A future opt-in `EVENT_CLIPS_ENABLED` flag may add short event clips —
keep it off unless the customer has explicit legal grounds.
