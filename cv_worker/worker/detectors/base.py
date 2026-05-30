"""Detector interface — keep small so swapping models is trivial."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class DetectionResult:
    people_count: int = 0
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDetector:
    """Subclasses must implement `detect(frame)` returning a DetectionResult.

    Implementations should be deterministic-on-input and never block on I/O.
    They should NOT persist anything (the pipeline owns persistence).
    """

    name: str = "base"

    def warmup(self) -> None:  # optional override
        return None

    def detect(self, frame: np.ndarray) -> DetectionResult:
        raise NotImplementedError
