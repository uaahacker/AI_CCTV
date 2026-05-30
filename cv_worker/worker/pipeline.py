"""
Per-camera pipeline: read frame → detect → persist → enqueue rules eval.

How CCTV computer-vision AI works in this project
-------------------------------------------------
1.  `RtspReader` opens the camera's RTSP/HTTP(S) stream with OpenCV (which
    delegates to ffmpeg/gstreamer under the hood) and decodes one frame at a
    time. Frames are pulled at SAMPLE_INTERVAL_SECONDS — we do NOT process
    every frame, both for CPU efficiency and for privacy (less raw data
    flowing through memory).
2.  The active `Detector` (DummyPeopleDetector for dev, YOLOPeopleDetector for
    production) returns the people count in the current frame. YOLO is loaded
    lazily on first use; it can be swapped for any object-detection model
    (COCO class 0 = "person"). Tracking/ID assignment would be added here
    to reduce double-counting across consecutive frames.
3.  The raw frame is DISCARDED. Only the integer count + confidence are
    persisted as a `DetectionEvent` row. No video is ever written to disk.
4.  A Celery task (`apps.alerts.tasks.evaluate_event`) is enqueued for each
    new event. That rules engine compares the count against active
    `AlertRule`s and may create an `Alert` + send email.
5.  An LLM provider (configured per-org in Settings → AI Settings) can then
    asynchronously summarise the Alert in plain English. The LLM only sees
    aggregate metadata — never raw imagery — and never participates in the
    detection decision itself.
"""
from __future__ import annotations

import logging
import threading
import time

from django.utils import timezone

from . import settings as cfg
from .detectors import BaseDetector
from .privacy import apply_privacy
from .stream import RtspReader

# Django models — safe to import: worker.settings already ran django.setup().
from apps.analytics.models import DetectionEvent  # noqa: E402
from apps.cameras.models import Camera, CameraHealthCheck  # noqa: E402

logger = logging.getLogger(__name__)


def _enqueue_rules_eval(event_id: str) -> None:
    """Fire-and-forget Celery dispatch for the Phase-4 rules engine."""
    try:
        from apps.alerts.tasks import evaluate_event

        evaluate_event.delay(str(event_id))
    except Exception:  # noqa: BLE001
        # If broker is down, don't kill the worker — we still saved the event.
        logger.exception("Failed enqueueing evaluate_event for %s", event_id)


def process_one(camera: Camera, detector: BaseDetector) -> None:
    """Single tick for one camera: read + detect + persist."""
    reader = RtspReader(camera.rtsp_url, open_timeout_s=cfg.RTSP_READ_TIMEOUT_SECONDS)
    result = reader.read_one()

    # --- Update health, regardless of detection success -------------------
    status = Camera.Status.ONLINE if result.ok else Camera.Status.OFFLINE
    CameraHealthCheck.objects.create(
        camera=camera,
        status=status,
        latency_ms=result.latency_ms,
        error_message=result.error,
    )
    camera.status = status
    camera.last_error = result.error
    if result.ok:
        camera.last_seen_at = timezone.now()
    camera.save(update_fields=["status", "last_error", "last_seen_at", "updated_at"])

    if not result.ok:
        logger.warning("Camera %s offline: %s", camera.name, result.error)
        return

    # --- Detection --------------------------------------------------------
    try:
        # Privacy preprocessing — blur faces BEFORE the detector sees the
        # frame. The detector receives an already-anonymised frame, so no
        # facial features ever influence the count or are passed downstream.
        frame = apply_privacy(result.frame)
        det = detector.detect(frame)
    except Exception:  # noqa: BLE001
        logger.exception("Detector failure for camera %s", camera.name)
        return

    event = DetectionEvent.objects.create(
        organization=camera.organization,
        camera=camera,
        event_type=DetectionEvent.EventType.PEOPLE_COUNT,
        people_count=det.people_count,
        confidence=det.confidence,
        metadata=det.metadata,
    )
    _enqueue_rules_eval(event.id)
    logger.info(
        "cam=%s people=%d conf=%.2f latency=%sms",
        camera.name, det.people_count, det.confidence, result.latency_ms,
    )


class CameraWorker(threading.Thread):
    """One thread per camera, sampling at SAMPLE_INTERVAL_SECONDS."""

    def __init__(self, camera_id: str, detector: BaseDetector, stop_event: threading.Event) -> None:
        super().__init__(name=f"cam-{camera_id[:8]}", daemon=True)
        self.camera_id = camera_id
        self.detector = detector
        self.stop_event = stop_event

    def run(self) -> None:
        logger.info("Starting worker thread for camera %s", self.camera_id)
        while not self.stop_event.is_set():
            try:
                cam = Camera.objects.select_related("organization").get(id=self.camera_id)
                if not cam.is_active:
                    logger.info("Camera %s deactivated, stopping thread", cam.name)
                    return
                process_one(cam, self.detector)
            except Camera.DoesNotExist:
                logger.info("Camera %s deleted, stopping thread", self.camera_id)
                return
            except Exception:  # noqa: BLE001
                logger.exception("Unhandled error in camera worker %s", self.camera_id)
                time.sleep(cfg.RECONNECT_BACKOFF_SECONDS)
            # Sleep is interruptible via the stop_event.
            self.stop_event.wait(cfg.SAMPLE_INTERVAL_SECONDS)
        logger.info("Stopped worker for camera %s", self.camera_id)
