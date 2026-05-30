"""
YOLO people detector — class index 0 == 'person' in COCO.

Heavy deps (ultralytics + torch) are imported lazily so dummy mode stays
zero-dependency.

Install: `pip install ultralytics`
Model weights are downloaded automatically on first run.
"""
from __future__ import annotations

import logging
import os

import numpy as np

from .base import BaseDetector, DetectionResult

logger = logging.getLogger(__name__)


class YOLOPeopleDetector(BaseDetector):
    name = "yolo"

    def __init__(self, model_path: str | None = None, conf: float | None = None) -> None:
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "ultralytics is not installed. Run `pip install ultralytics` "
                "or set DETECTOR=dummy."
            ) from exc

        self.model_path = model_path or os.environ.get("YOLO_MODEL", "yolov8n.pt")
        self.conf = conf if conf is not None else float(os.environ.get("YOLO_CONF", "0.35"))
        logger.info("Loading YOLO weights: %s", self.model_path)
        self.model = YOLO(self.model_path)

    def detect(self, frame: np.ndarray) -> DetectionResult:
        # ultralytics expects BGR / RGB ndarray — passes through to the predictor.
        results = self.model.predict(frame, conf=self.conf, classes=[0], verbose=False)
        if not results:
            return DetectionResult()
        r0 = results[0]
        boxes = r0.boxes
        n = int(boxes.shape[0]) if boxes is not None else 0
        avg_conf = float(boxes.conf.mean().item()) if n else 0.0

        # Normalise xyxy to [0,1] so downstream tracking is frame-size-agnostic.
        h, w = frame.shape[:2]
        bbox_list: list[dict] = []
        if n and getattr(boxes, "xyxy", None) is not None:
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            for (x1, y1, x2, y2), c in zip(xyxy, confs):
                bbox_list.append({
                    "bbox": [float(x1) / w, float(y1) / h, float(x2) / w, float(y2) / h],
                    "confidence": float(c),
                    "label": "person",
                })

        return DetectionResult(
            people_count=n,
            confidence=round(avg_conf, 3),
            metadata={"detector": self.name, "model": self.model_path, "boxes": bbox_list},
        )
