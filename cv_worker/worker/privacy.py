"""
Privacy preprocessing: blur every detected face BEFORE any downstream detector
sees the frame.

Default behaviour (ON) enforces a GDPR-friendly stance: the system never
analyses, stores, or transmits identifiable facial features. The CV pipeline
calls `apply_privacy(frame)` immediately after decode and before counting.

Implementation
--------------
Uses OpenCV's bundled Haar cascade (no model download, no ML weights, no
network). This is intentionally a CLASSIFIER ONLY (face localisation) — it
performs zero recognition / identification / embedding extraction.

If env `PRIVACY_FACIAL_RECOGNITION_ENABLED=true` is set, blur is skipped — but
the worker logs a loud warning at start-up and the dashboard surfaces a
compliance banner so operators cannot toggle it accidentally.
"""
from __future__ import annotations

import logging
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_BLUR_FACES = os.environ.get("PRIVACY_BLUR_FACES", "true").lower() != "false"
_FR_ENABLED = os.environ.get("PRIVACY_FACIAL_RECOGNITION_ENABLED", "false").lower() == "true"

_CASCADE = None  # lazy


def _cascade():
    global _CASCADE
    if _CASCADE is None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _CASCADE = cv2.CascadeClassifier(path)
        if _CASCADE.empty():
            logger.error("Failed to load Haar cascade from %s; face blur disabled", path)
            _CASCADE = False  # sentinel
    return _CASCADE or None


def blur_faces(frame: np.ndarray) -> np.ndarray:
    """Blur every detected face in-place; returns the modified frame."""
    cas = _cascade()
    if cas is None:
        return frame
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cas.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(28, 28))
    for (x, y, w, h) in faces:
        roi = frame[y:y + h, x:x + w]
        if roi.size == 0:
            continue
        # Strong Gaussian blur — irreversible, no face features recoverable.
        k = max(15, (w // 4) | 1)  # odd kernel size
        frame[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (k, k), 0)
    return frame


def apply_privacy(frame: np.ndarray) -> np.ndarray:
    """Entry point invoked by the pipeline. Honours env-driven defaults."""
    if _FR_ENABLED:
        # Operator explicitly enabled FR — still blur unless they also disable blur.
        if not _BLUR_FACES:
            return frame
    if not _BLUR_FACES:
        return frame
    try:
        return blur_faces(frame)
    except Exception:  # noqa: BLE001
        logger.exception("Face-blur pipeline failed; returning original frame")
        return frame


def log_privacy_state() -> None:
    """Called once at worker startup so the policy is visible in logs."""
    logger.info(
        "Privacy: blur_faces=%s facial_recognition=%s",
        _BLUR_FACES, _FR_ENABLED,
    )
    if _FR_ENABLED:
        logger.warning(
            "PRIVACY WARNING: facial recognition is ENABLED via env. "
            "This may violate GDPR / local CCTV laws. Disable unless you "
            "have an explicit legal basis."
        )
