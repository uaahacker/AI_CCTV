"""Lightweight centroid + IoU tracker — pure stdlib, no deep-learning model.

The tracker assigns a stable integer id to each detection across consecutive
frames so downstream analytics (line crossing, dwell time, abandoned object
detection) can reason about "the same object".

This is intentionally simple — it is NOT SORT/DeepSORT. It uses bounding-box
IoU + centroid distance for matching and drops a track after ``max_age`` ticks
without an update. Good enough for parking and zone analytics at sampled
frame rates (1-2 fps). Swap in DeepSORT later if multi-object re-ID becomes
important.
"""
from __future__ import annotations

import itertools
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Detection:
    """A single detection from the detector."""

    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2) — normalised [0,1]
    confidence: float = 0.0
    label: str = "person"


@dataclass
class Track:
    """A persistent track across frames."""

    track_id: int
    bbox: tuple[float, float, float, float]
    label: str
    first_seen: float
    last_seen: float
    confidence: float
    history: deque = field(default_factory=lambda: deque(maxlen=120))  # centroids
    misses: int = 0

    @property
    def centroid(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def age_seconds(self) -> float:
        return self.last_seen - self.first_seen

    def is_stationary(self, *, radius: float = 0.02) -> bool:
        """True if the last ~30 centroids are all within ``radius`` of the latest."""
        if len(self.history) < 10:
            return False
        cx, cy = self.history[-1]
        for px, py in list(self.history)[-30:]:
            if ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 > radius:
                return False
        return True


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    a_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = a_area + b_area - inter
    return inter / union if union else 0.0


class CentroidTracker:
    """Greedy IoU-based tracker.

    Parameters
    ----------
    iou_threshold:
        Matches with IoU below this are rejected.
    max_age:
        Number of consecutive missed updates before a track is dropped.
    """

    def __init__(self, *, iou_threshold: float = 0.2, max_age: int = 5) -> None:
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self._tracks: dict[int, Track] = {}
        self._id_seq = itertools.count(1)

    @property
    def tracks(self) -> list[Track]:
        return list(self._tracks.values())

    def update(self, detections: Iterable[Detection]) -> list[Track]:
        now = time.time()
        dets = list(detections)
        unmatched_track_ids = set(self._tracks.keys())
        unmatched_det_idx = set(range(len(dets)))

        # Score every (track, detection) pair and greedily pick the best.
        pairs: list[tuple[float, int, int]] = []
        for tid, trk in self._tracks.items():
            for i, det in enumerate(dets):
                if det.label != trk.label:
                    continue
                score = _iou(trk.bbox, det.bbox)
                if score >= self.iou_threshold:
                    pairs.append((score, tid, i))
        pairs.sort(reverse=True)

        for _score, tid, i in pairs:
            if tid in unmatched_track_ids and i in unmatched_det_idx:
                trk = self._tracks[tid]
                det = dets[i]
                trk.bbox = det.bbox
                trk.confidence = det.confidence
                trk.last_seen = now
                trk.misses = 0
                trk.history.append(trk.centroid)
                unmatched_track_ids.discard(tid)
                unmatched_det_idx.discard(i)

        # New tracks for unmatched detections.
        for i in unmatched_det_idx:
            det = dets[i]
            new_id = next(self._id_seq)
            trk = Track(
                track_id=new_id,
                bbox=det.bbox,
                label=det.label,
                first_seen=now,
                last_seen=now,
                confidence=det.confidence,
            )
            trk.history.append(trk.centroid)
            self._tracks[new_id] = trk

        # Age out unmatched tracks.
        for tid in list(unmatched_track_ids):
            trk = self._tracks[tid]
            trk.misses += 1
            if trk.misses > self.max_age:
                del self._tracks[tid]

        return list(self._tracks.values())
