from .base import BaseDetector, DetectionResult
from .dummy import DummyPeopleDetector


def get_detector(name: str) -> BaseDetector:
    name = (name or "dummy").lower()
    if name == "dummy":
        return DummyPeopleDetector()
    if name == "yolo":
        # Imported lazily so dummy mode doesn't require ultralytics installed.
        from .yolo import YOLOPeopleDetector

        return YOLOPeopleDetector()
    raise ValueError(f"Unknown detector: {name}")


__all__ = ["BaseDetector", "DetectionResult", "DummyPeopleDetector", "get_detector"]
