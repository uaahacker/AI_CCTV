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
    production) returns per-frame detections. YOLO is loaded lazily on first
    use; bounding boxes feed the centroid tracker so the same physical
    object keeps a stable ID across consecutive frames.
3.  The `CentroidTracker` + `CameraAnalytics` derive higher-level events
    from those tracks: zone entry / exit, line crossing, loitering,
    abandoned object, queue length. A `ParkingMonitor` derives slot states
    (FREE / OCCUPIED / ILLEGAL) for any zone with kind=parking_slot.
4.  An optional `RollingClipBuffer` keeps the last EVIDENCE_CLIP_SECONDS of
    decoded frames in memory. When an alertable event fires we flush them
    to an MP4 under MEDIA_ROOT/clips/<camera>/<event>.mp4 and stash the
    relative path in DetectionEvent.metadata so the rules engine can attach
    it to the resulting Alert.
5.  Frames are then DISCARDED. Only counts + confidences + bbox metadata
    are persisted as `DetectionEvent` rows.
6.  A Celery task (`apps.alerts.tasks.evaluate_event`) is enqueued for each
    new event. That rules engine compares the count against active
    `AlertRule`s and may create an `Alert` + send notifications.
7.  An LLM provider can asynchronously summarise the Alert in plain
    English. The LLM only sees aggregate metadata — never raw imagery — and
    never participates in the detection decision itself.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from . import settings as cfg
from .analytics import CameraAnalytics, ZoneConfig
from .clipbuf import RollingClipBuffer
from .detectors import BaseDetector
from .heatmap import HeatmapAccumulator, hour_bucket_now
from .parking import ParkingMonitor
from .privacy import apply_privacy
from .stream import RtspReader
from .tracking import CentroidTracker, Detection

# Django models — safe to import: worker.settings already ran django.setup().
from django.conf import settings as dj_settings  # noqa: E402
from django.db.models import F  # noqa: E402

from apps.analytics.models import DetectionEvent, HeatmapBucket, ParkingSlotState  # noqa: E402
from apps.cameras.models import Camera, CameraHealthCheck, Zone  # noqa: E402

logger = logging.getLogger(__name__)

# Event types that warrant flushing a rolling evidence clip.
_CLIPPABLE_EVENTS = {
    DetectionEvent.EventType.PEOPLE_COUNT,
    DetectionEvent.EventType.LOITERING,
    DetectionEvent.EventType.ABANDONED_OBJECT,
    DetectionEvent.EventType.LINE_CROSSING,
    DetectionEvent.EventType.PARKING_ILLEGAL,
}


def _enqueue_rules_eval(event_id: str) -> None:
    """Fire-and-forget Celery dispatch for the Phase-4 rules engine."""
    try:
        from apps.alerts.tasks import evaluate_event

        evaluate_event.delay(str(event_id))
    except Exception:  # noqa: BLE001
        # If broker is down, don't kill the worker — we still saved the event.
        logger.exception("Failed enqueueing evaluate_event for %s", event_id)


def _load_zones(camera: Camera) -> list[ZoneConfig]:
    """Snapshot of active zones for this camera, as plain DTOs."""
    out: list[ZoneConfig] = []
    for z in Zone.objects.filter(camera=camera, is_active=True):
        out.append(ZoneConfig(
            id=str(z.id),
            name=z.name,
            kind=z.kind,
            geometry=z.geometry or [],
            direction=z.direction,
            config=z.config or {},
        ))
    return out


def _detections_from_metadata(det_metadata: dict) -> list[Detection]:
    boxes = det_metadata.get("boxes") if isinstance(det_metadata, dict) else None
    if not isinstance(boxes, list):
        return []
    out: list[Detection] = []
    for b in boxes:
        bbox = b.get("bbox")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            continue
        out.append(Detection(
            bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
            confidence=float(b.get("confidence") or 0.0),
            label=str(b.get("label") or "person"),
        ))
    return out


def _flush_heatmap(camera: Camera, accumulator: HeatmapAccumulator) -> None:
    counts = accumulator.drain()
    if not counts:
        return
    bucket = hour_bucket_now()
    for (gx, gy), weight in counts.items():
        obj, created = HeatmapBucket.objects.get_or_create(
            camera=camera, hour_bucket=bucket, grid_x=gx, grid_y=gy,
            defaults={"weight": weight},
        )
        if not created:
            HeatmapBucket.objects.filter(pk=obj.pk).update(weight=F("weight") + weight)


def _persist_event(
    *, camera: Camera, event_type: str, people_count: int, confidence: float,
    metadata: dict, clip_buffer: RollingClipBuffer | None,
) -> str:
    event = DetectionEvent.objects.create(
        organization=camera.organization,
        camera=camera,
        event_type=event_type,
        people_count=people_count,
        confidence=confidence,
        metadata=metadata,
    )
    if (
        clip_buffer is not None
        and cfg.EVIDENCE_CLIPS_ENABLED
        and event_type in _CLIPPABLE_EVENTS
    ):
        rel = clip_buffer.flush(camera_id=str(camera.id), event_id=str(event.id))
        if rel:
            metadata = {**metadata, "clip_path": rel}
            DetectionEvent.objects.filter(pk=event.pk).update(metadata=metadata)
    _enqueue_rules_eval(event.id)
    return str(event.id)


class _CameraState:
    """Encapsulates the per-camera state objects that live for the lifetime
    of the worker thread."""

    __slots__ = ("tracker", "analytics", "parking", "heatmap", "clipbuf", "ticks_since_flush")

    def __init__(self, camera_id: str) -> None:
        self.tracker = CentroidTracker()
        self.analytics = CameraAnalytics()
        self.parking = ParkingMonitor()
        self.heatmap = HeatmapAccumulator()
        media_root = str(getattr(dj_settings, "MEDIA_ROOT", "media"))
        fps = max(1.0, 1.0 / max(0.5, cfg.SAMPLE_INTERVAL_SECONDS))
        self.clipbuf = RollingClipBuffer(
            fps=fps, seconds=cfg.EVIDENCE_CLIP_SECONDS, output_root=media_root,
        )
        self.ticks_since_flush = 0


def process_one(camera: Camera, detector: BaseDetector, state: _CameraState | None = None) -> None:
    """Single tick for one camera: read + detect + track + persist."""
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

    # Push the privacy-filtered frame into the rolling buffer so any clip we
    # write later contains the same anonymised pixels the detector saw.
    if state is not None:
        state.clipbuf.push(frame)

    # Strip the heavy bbox list out before persistence — we keep a compact
    # summary in metadata, and the rich bbox info is only needed in-memory.
    metadata_for_db = {k: v for k, v in (det.metadata or {}).items() if k != "boxes"}
    metadata_for_db["bbox_count"] = len(det.metadata.get("boxes", []) if det.metadata else [])

    event_id = _persist_event(
        camera=camera,
        event_type=DetectionEvent.EventType.PEOPLE_COUNT,
        people_count=det.people_count,
        confidence=det.confidence,
        metadata=metadata_for_db,
        clip_buffer=state.clipbuf if state else None,
    )
    logger.info(
        "cam=%s people=%d conf=%.2f latency=%sms event=%s",
        camera.name, det.people_count, det.confidence, result.latency_ms, event_id,
    )

    if state is None or not cfg.ENABLE_TRACKING:
        return

    # --- Tracking + zone analytics ---------------------------------------
    detections = _detections_from_metadata(det.metadata or {})
    tracks = state.tracker.update(detections)

    for trk in tracks:
        cx, cy = trk.centroid
        state.heatmap.add_point(cx, cy)

    zones = _load_zones(camera)
    polygon_and_line = [z for z in zones if z.kind in ("polygon", "line")]
    slot_zones = [z for z in zones if z.kind == "parking_slot"]

    analytics_events = state.analytics.process(tracks, polygon_and_line)
    snapshots, parking_events = state.parking.update(tracks, slot_zones)

    # Persist parking slot state for the dashboard /api/analytics/parking/.
    for snap in snapshots:
        since_dt = datetime.fromtimestamp(snap.since, tz=dt_timezone.utc)
        ParkingSlotState.objects.update_or_create(
            zone_id=snap.zone_id,
            defaults={
                "state": snap.state,
                "since": since_dt,
                "vehicle_track_id": snap.vehicle_track_id,
            },
        )

    # Emit high-level events. We re-use _persist_event so each gets the
    # rules-engine dispatch + optional clip attachment.
    for ev in analytics_events + parking_events:
        et = ev.pop("event_type")
        _persist_event(
            camera=camera,
            event_type=et,
            people_count=ev.get("count", 0) or 0,
            confidence=det.confidence,
            metadata=ev,
            clip_buffer=state.clipbuf,
        )

    # Flush heatmap counts every N ticks to keep DB writes bounded.
    state.ticks_since_flush += 1
    if state.ticks_since_flush >= cfg.HEATMAP_FLUSH_EVERY_TICKS:
        try:
            _flush_heatmap(camera, state.heatmap)
        except Exception:  # noqa: BLE001
            logger.exception("Heatmap flush failed for camera %s", camera.name)
        state.ticks_since_flush = 0


class CameraWorker(threading.Thread):
    """One thread per camera, sampling at SAMPLE_INTERVAL_SECONDS."""

    def __init__(self, camera_id: str, detector: BaseDetector, stop_event: threading.Event) -> None:
        super().__init__(name=f"cam-{camera_id[:8]}", daemon=True)
        self.camera_id = camera_id
        self.detector = detector
        self.stop_event = stop_event
        self._state = _CameraState(camera_id)

    def run(self) -> None:
        logger.info("Starting worker thread for camera %s", self.camera_id)
        while not self.stop_event.is_set():
            try:
                cam = Camera.objects.select_related("organization").get(id=self.camera_id)
                if not cam.is_active:
                    logger.info("Camera %s deactivated, stopping thread", cam.name)
                    return
                process_one(cam, self.detector, self._state)
            except Camera.DoesNotExist:
                logger.info("Camera %s deleted, stopping thread", self.camera_id)
                return
            except Exception:  # noqa: BLE001
                logger.exception("Unhandled error in camera worker %s", self.camera_id)
                time.sleep(cfg.RECONNECT_BACKOFF_SECONDS)
            # Sleep is interruptible via the stop_event.
            self.stop_event.wait(cfg.SAMPLE_INTERVAL_SECONDS)
        # Best-effort final flush so we don't lose the last hour's heatmap data.
        try:
            cam = Camera.objects.get(id=self.camera_id)
            _flush_heatmap(cam, self._state.heatmap)
        except Exception:  # noqa: BLE001
            pass
        logger.info("Stopped worker for camera %s", self.camera_id)

