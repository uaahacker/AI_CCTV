"""Celery application — autodiscovers tasks across apps."""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("aicctv")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# --- Beat schedule -------------------------------------------------------
# Run with:  celery -A config beat -l info
app.conf.beat_schedule = {
    "alerts.check-offline-cameras": {
        "task": "apps.alerts.tasks.check_offline_cameras",
        "schedule": crontab(minute="*/2"),  # every 2 minutes
        "kwargs": {"max_age_minutes": 5},
    },
    "alerts.generate-daily-reports": {
        "task": "apps.alerts.tasks.generate_daily_reports",
        # 07:00 server-local — change per deployment if needed.
        "schedule": crontab(hour=7, minute=0),
    },
}


@app.task(bind=True)
def debug_task(self) -> None:  # pragma: no cover - dev helper
    print(f"Request: {self.request!r}")
