"""
YOLO multi-class detector — detects people and common vehicles.

COCO classes used:
  0  person
  1  bicycle
  2  car
  3  motorcycle
  5  bus
  7  truck

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

# COCO class id → normalised label we use across the project. Anything not
# in this map is ignored by the detector.
_COCO_LABELS = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Vehicle labels grouped for `class_counts.vehicles` rollup.
_VEHICLE_LABELS = {"bicycle", "car", "motorcycle", "bus", "truck"}


class YOLOPeopleDetector(BaseDetector):
    """YOLO detector that reports persons + vehicles.

    The class is named ``YOLOPeopleDetector`` for backwards compatibility —
    ``people_count`` on the result still means *persons only* so existing
    rules (people_count threshold, crowd, etc.) keep working. The full
    breakdown is in ``metadata['class_counts']``.
    """

    name = "yolo"

    def __init__(self, model_path: str | None = None, conf: float | None = None) -> None:
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "ultralytics is not installed. Run `pip install ultralytics` "
                "or set DETECTOR=dummy."
            ) from exc

        # PyTorch 2.6 flipped torch.load(weights_only=) to True by default.
        # Ultralytics < 8.3 doesn't whitelist its own classes, so loading
        # an official yolov8n.pt blows up with `Unsupported global`. We
        # explicitly allow-list the ultralytics + torch.nn modules used in
        # the official checkpoints. Safe because we control the URL the
        # model is downloaded from (github.com/ultralytics/assets).
        try:
            import torch  # type: ignore
            import torch.nn as nn  # type: ignore

            extra_globals: list = [nn.modules.container.Sequential]
            try:
                from ultralytics.nn import tasks as _ul_tasks  # type: ignore
                from ultralytics.nn import modules as _ul_modules  # type: ignore

                # Whitelist the top-level model class + every nn module ultralytics
                # ships, so any version's checkpoint deserialises cleanly.
                for name in dir(_ul_tasks):
                    obj = getattr(_ul_tasks, name)
                    if isinstance(obj, type):
                        extra_globals.append(obj)
                for sub in ("conv", "block", "head", "transformer", "utils"):
                    try:
                        mod = getattr(_ul_modules, sub)
                    except AttributeError:
                        continue
                    for name in dir(mod):
                        obj = getattr(mod, name)
                        if isinstance(obj, type):
                            extra_globals.append(obj)
            except Exception:  # noqa: BLE001
                pass
            if hasattr(torch.serialization, "add_safe_globals"):
                torch.serialization.add_safe_globals(extra_globals)
        except Exception:  # noqa: BLE001
            pass

        self.model_path = model_path or os.environ.get("YOLO_MODEL", "yolov8n.pt")
        self.conf = conf if conf is not None else float(os.environ.get("YOLO_CONF", "0.35"))
        logger.info("Loading YOLO weights: %s (conf>=%.2f)", self.model_path, self.conf)
        self.model = YOLO(self.model_path)
        self._class_ids = sorted(_COCO_LABELS.keys())

    def detect(self, frame: np.ndarray) -> DetectionResult:
        results = self.model.predict(
            frame, conf=self.conf, classes=self._class_ids, verbose=False
        )
        if not results:
            return DetectionResult()
        r0 = results[0]
        boxes = r0.boxes
        if boxes is None or boxes.shape[0] == 0:
            return DetectionResult(metadata={
                "detector": self.name,
                "model": self.model_path,
                "boxes": [],
                "class_counts": {},
            })

        h, w = frame.shape[:2]
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        cls   = boxes.cls.cpu().numpy().astype(int)

        bbox_list: list[dict] = []
        class_counts: dict[str, int] = {}
        people_count = 0
        people_confs: list[float] = []

        for (x1, y1, x2, y2), c, k in zip(xyxy, confs, cls):
            label = _COCO_LABELS.get(int(k))
            if not label:
                continue
            bbox_list.append({
                "bbox": [float(x1) / w, float(y1) / h, float(x2) / w, float(y2) / h],
                "confidence": float(c),
                "label": label,
            })
            class_counts[label] = class_counts.get(label, 0) + 1
            if label == "person":
                people_count += 1
                people_confs.append(float(c))

        # Rollups for the dashboard.
        class_counts["vehicles"] = sum(class_counts.get(v, 0) for v in _VEHICLE_LABELS)

        avg_conf = round(sum(people_confs) / len(people_confs), 3) if people_confs else 0.0

        return DetectionResult(
            people_count=people_count,
            confidence=avg_conf,
            metadata={
                "detector": self.name,
                "model": self.model_path,
                "boxes": bbox_list,
                "class_counts": class_counts,
            },
        )
