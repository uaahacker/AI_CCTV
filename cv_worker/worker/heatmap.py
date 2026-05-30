"""Per-camera heatmap accumulator.

Each tick we bucket the centroid of every active track into a 16×16 grid and
flush periodically to ``HeatmapBucket`` (one row per (camera, hour, x, y)).
This keeps the write rate bounded — at worst 16×16 = 256 rows per camera per
hour, regardless of frame rate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class HeatmapAccumulator:
    grid_size: int = 16
    # (grid_x, grid_y) -> count, for the current hour
    _counts: dict[tuple[int, int], int] = field(default_factory=dict)

    def add_point(self, x: float, y: float) -> None:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return
        gx = min(self.grid_size - 1, int(x * self.grid_size))
        gy = min(self.grid_size - 1, int(y * self.grid_size))
        self._counts[(gx, gy)] = self._counts.get((gx, gy), 0) + 1

    def drain(self) -> dict[tuple[int, int], int]:
        out = self._counts
        self._counts = {}
        return out


def hour_bucket_now() -> datetime:
    """Return the current UTC hour, truncated to minute=second=microsecond=0."""
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0)
