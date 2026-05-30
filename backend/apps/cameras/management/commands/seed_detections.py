"""
Seed a synthetic DetectionEvent for every active camera.

Useful for exercising the dashboard / reports / rules engine without setting
up the CV worker. Run:

    python manage.py seed_detections --count 50

(Optional --camera <uuid> limits to one camera.)
"""
from __future__ import annotations

import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.analytics.models import DetectionEvent
from apps.cameras.models import Camera


class Command(BaseCommand):
    help = "Generate synthetic DetectionEvent rows for development."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=20)
        parser.add_argument("--camera", type=str, default=None)
        parser.add_argument("--max", type=int, default=15, help="Max people count.")

    def handle(self, *args, **opts):
        qs = Camera.objects.filter(is_active=True)
        if opts["camera"]:
            qs = qs.filter(id=opts["camera"])
        cams = list(qs.select_related("organization"))
        if not cams:
            self.stderr.write("No active cameras found.")
            return

        created = 0
        for _ in range(opts["count"]):
            for cam in cams:
                DetectionEvent.objects.create(
                    organization=cam.organization,
                    camera=cam,
                    event_type=DetectionEvent.EventType.PEOPLE_COUNT,
                    people_count=random.randint(0, opts["max"]),
                    confidence=round(random.uniform(0.5, 0.95), 2),
                    metadata={"seed": True, "ts": timezone.now().isoformat()},
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} detection events."))
