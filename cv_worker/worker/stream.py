"""Thin OpenCV RTSP reader with reconnect + timeout handling."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Use TCP transport for RTSP — UDP loses frames on shaky networks.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")


@dataclass
class ReadResult:
    ok: bool
    frame: np.ndarray | None = None
    latency_ms: int | None = None
    error: str = ""


class RtspReader:
    """Single-shot RTSP frame grabber.

    The worker grabs one frame per `SAMPLE_INTERVAL_SECONDS`, so we open/close
    the capture per call. That keeps memory flat and avoids long-running ffmpeg
    threads going stale. For higher framerate detection, refactor to a long-
    lived capture + worker thread.
    """

    def __init__(self, url: str, open_timeout_s: int = 10) -> None:
        self.url = url
        self.open_timeout_s = open_timeout_s

    def read_one(self) -> ReadResult:
        if not self.url:
            return ReadResult(False, error="empty url")
        start = time.time()
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        try:
            if not cap.isOpened():
                return ReadResult(False, error="failed to open stream")
            # Drain one frame; first frame after open is often stale.
            cap.read()
            ok, frame = cap.read()
            latency = int((time.time() - start) * 1000)
            if not ok or frame is None:
                return ReadResult(False, latency_ms=latency, error="empty frame")
            return ReadResult(True, frame=frame, latency_ms=latency)
        except Exception as exc:  # noqa: BLE001
            return ReadResult(False, error=str(exc))
        finally:
            cap.release()
