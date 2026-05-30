"""
CV worker entrypoint.

Run:  python -m worker.main

Refreshes the active-camera list periodically, spawns/stops per-camera threads,
and shuts down cleanly on SIGINT.
"""
from __future__ import annotations

# Bootstrap Django FIRST — must come before any apps.* import.
from . import settings as cfg  # noqa: F401  (side effect: django.setup())

import logging
import signal
import threading
import time

from apps.cameras.models import Camera  # noqa: E402

from .detectors import get_detector  # noqa: E402
from .pipeline import CameraWorker  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cv_worker")

# --- Sentry (optional) --------------------------------------------------
# Pulled in from env directly; the cv_worker is intentionally a thin
# process that doesn't import Django settings. Zero overhead when unset.
import os as _os
_sentry_dsn = _os.environ.get("SENTRY_DSN", "").strip()
if _sentry_dsn:
    try:
        import sentry_sdk  # type: ignore

        sentry_sdk.init(
            dsn=_sentry_dsn,
            environment=_os.environ.get("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=float(_os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0") or 0.0),
            send_default_pii=False,
        )
        logger.info("Sentry SDK enabled for cv_worker")
    except Exception:  # pragma: no cover
        logger.warning("Sentry init failed", exc_info=True)


def main() -> int:
    from .privacy import log_privacy_state
    log_privacy_state()
    detector = get_detector(cfg.DETECTOR)
    logger.info("Using detector: %s", detector.name)
    try:
        detector.warmup()
    except Exception:  # noqa: BLE001
        logger.exception("Detector warmup failed; continuing")

    stop_event = threading.Event()

    def handle_signal(signum, _frame):
        logger.info("Signal %s received — shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    workers: dict[str, CameraWorker] = {}

    while not stop_event.is_set():
        try:
            active_ids = set(
                str(i) for i in Camera.objects.filter(is_active=True).values_list("id", flat=True)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed loading camera list — retrying")
            stop_event.wait(cfg.CAMERA_REFRESH_SECONDS)
            continue

        if len(active_ids) > cfg.MAX_CAMERAS:
            logger.warning(
                "Active cameras (%d) exceed MAX_CAMERAS (%d) — only the first %d will run",
                len(active_ids), cfg.MAX_CAMERAS, cfg.MAX_CAMERAS,
            )
            active_ids = set(list(active_ids)[: cfg.MAX_CAMERAS])

        # Start new ones
        for cid in active_ids - set(workers):
            w = CameraWorker(cid, detector, stop_event)
            w.start()
            workers[cid] = w

        # Reap dead / deactivated ones
        for cid in list(workers):
            if cid not in active_ids or not workers[cid].is_alive():
                logger.info("Releasing worker slot for camera %s", cid)
                workers.pop(cid, None)

        logger.info("Supervising %d camera thread(s)", len(workers))
        stop_event.wait(cfg.CAMERA_REFRESH_SECONDS)

    # Graceful shutdown
    logger.info("Waiting for worker threads to finish…")
    deadline = time.time() + 10
    for w in workers.values():
        remaining = max(0.1, deadline - time.time())
        w.join(timeout=remaining)
    logger.info("Bye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
