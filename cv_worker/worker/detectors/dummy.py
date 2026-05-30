"""Synthetic detector — produces a smoothly varying people count so the
dashboard, reports and rules engine can be exercised end-to-end without GPUs."""
from __future__ import annotations

import math
import os
import random
import time

import numpy as np

from .base import BaseDetector, DetectionResult


class DummyPeopleDetector(BaseDetector):
    name = "dummy"

    def __init__(self, amplitude: int | None = None) -> None:
        self.amplitude = amplitude or int(os.environ.get("DUMMY_MAX_PEOPLE", "15"))
        self._t0 = time.time()

    def detect(self, frame: np.ndarray) -> DetectionResult:
        # Sine wave + small noise, never negative.
        t = time.time() - self._t0
        base = (math.sin(t / 30.0) + 1) / 2  # 0..1 over ~3 minute period
        noise = random.uniform(-0.1, 0.1)
        count = max(0, round((base + noise) * self.amplitude))
        return DetectionResult(
            people_count=count,
            confidence=round(0.6 + random.uniform(0, 0.3), 3),
            metadata={
                "detector": self.name,
                "frame_shape": list(frame.shape) if frame is not None else None,
            },
        )
