"""Per-camera analytics state + emitters.

Drives the higher-level event types (zone entry/exit, line crossings,
loitering, abandoned object, queue length). Each ``CameraAnalytics`` instance
is stateful — it remembers which tracks were inside which polygon last tick
so it can emit IN/OUT transitions.

It returns a list of plain dicts; ``pipeline.py`` is responsible for actually
persisting them as ``DetectionEvent`` rows. That separation keeps this
module trivially unit-testable without a Django DB.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .tracking import Track
from .zones import line_direction, point_in_polygon, polygon_pairs, segments_intersect


@dataclass
class ZoneConfig:
    """Plain DTO mirroring ``apps.cameras.models.Zone`` — kept decoupled
    so the worker can mock zones easily."""

    id: str
    name: str
    kind: str  # 'polygon' | 'line' | 'parking_slot'
    geometry: list  # list of [x, y] pairs
    direction: str = "NONE"  # 'NONE' | 'IN' | 'OUT' | 'BOTH'
    config: dict = field(default_factory=dict)


@dataclass
class CameraAnalytics:
    """Holds per-zone, per-track state between ticks."""

    # zone_id -> set of track_ids currently inside that polygon
    _inside: dict[str, set[int]] = field(default_factory=dict)
    # track_id -> centroid from last tick (for line-crossing direction)
    _last_centroid: dict[int, tuple[float, float]] = field(default_factory=dict)
    # zone_id -> {track_id: entered_at_timestamp}  (for loitering)
    _dwell_start: dict[str, dict[int, float]] = field(default_factory=dict)
    # zone_id -> set of already-emitted loiter alerts (track_id) to avoid spam
    _loiter_emitted: dict[str, set[int]] = field(default_factory=dict)
    # track_id -> first_seen_stationary_at (for abandoned)
    _abandoned_emitted: set[int] = field(default_factory=set)

    def process(self, tracks: list[Track], zones: list[ZoneConfig]) -> list[dict]:
        now = time.time()
        events: list[dict] = []
        current_centroid = {t.track_id: t.centroid for t in tracks}

        for z in zones:
            if z.kind == "polygon":
                events.extend(self._handle_polygon(z, tracks, now))
            elif z.kind == "line":
                events.extend(self._handle_line(z, tracks, current_centroid))
            # parking_slot is handled by parking.ParkingMonitor

        # Abandoned objects: a stationary track that lives long enough.
        events.extend(self._handle_abandoned(tracks, now))

        # Stash for next tick.
        self._last_centroid = current_centroid

        # Drop state for tracks that have disappeared.
        live_ids = set(current_centroid)
        for zid, ids in list(self._inside.items()):
            self._inside[zid] = ids & live_ids
        for zid, dwell in list(self._dwell_start.items()):
            self._dwell_start[zid] = {tid: t for tid, t in dwell.items() if tid in live_ids}
        for zid, ids in list(self._loiter_emitted.items()):
            self._loiter_emitted[zid] = ids & live_ids
        self._abandoned_emitted &= live_ids

        return events

    # ---------- handlers ----------------------------------------------------

    def _handle_polygon(self, z: ZoneConfig, tracks: list[Track], now: float) -> list[dict]:
        polygon = polygon_pairs(z.geometry)
        if len(polygon) < 3:
            return []
        prev_inside = self._inside.get(z.id, set())
        new_inside: set[int] = set()
        dwell = self._dwell_start.setdefault(z.id, {})
        loiter_emitted = self._loiter_emitted.setdefault(z.id, set())
        dwell_threshold = float(z.config.get("dwell_seconds") or 0)

        events: list[dict] = []
        for trk in tracks:
            if point_in_polygon(trk.centroid, polygon):
                new_inside.add(trk.track_id)
                if trk.track_id not in prev_inside:
                    events.append({
                        "event_type": "zone_entry",
                        "zone_id": z.id,
                        "track_id": trk.track_id,
                        "centroid": list(trk.centroid),
                    })
                    dwell[trk.track_id] = now
                elif (
                    dwell_threshold
                    and trk.track_id not in loiter_emitted
                    and (now - dwell.get(trk.track_id, now)) >= dwell_threshold
                ):
                    events.append({
                        "event_type": "loitering",
                        "zone_id": z.id,
                        "track_id": trk.track_id,
                        "dwell_seconds": now - dwell.get(trk.track_id, now),
                    })
                    loiter_emitted.add(trk.track_id)

        for tid in prev_inside - new_inside:
            events.append({
                "event_type": "zone_exit",
                "zone_id": z.id,
                "track_id": tid,
            })
            dwell.pop(tid, None)
            loiter_emitted.discard(tid)

        self._inside[z.id] = new_inside

        # Queue-length: emit once per tick for the current count if requested.
        if z.config.get("queue_length"):
            events.append({
                "event_type": "queue_length",
                "zone_id": z.id,
                "count": len(new_inside),
            })

        return events

    def _handle_line(
        self,
        z: ZoneConfig,
        tracks: list[Track],
        current_centroid: dict[int, tuple[float, float]],
    ) -> list[dict]:
        pts = polygon_pairs(z.geometry)
        if len(pts) != 2:
            return []
        p1, p2 = pts[0], pts[1]
        events: list[dict] = []
        for trk in tracks:
            prev = self._last_centroid.get(trk.track_id)
            if not prev:
                continue
            curr = current_centroid[trk.track_id]
            if segments_intersect(p1, p2, prev, curr):
                direction = line_direction(p1, p2, prev, curr)
                if z.direction != "NONE" and z.direction != "BOTH" and z.direction != direction:
                    continue
                events.append({
                    "event_type": "line_crossing",
                    "zone_id": z.id,
                    "track_id": trk.track_id,
                    "direction": direction,
                })
        return events

    def _handle_abandoned(self, tracks: list[Track], now: float) -> list[dict]:
        events: list[dict] = []
        for trk in tracks:
            if trk.label == "person":
                continue  # people aren't "abandoned" — that's loitering
            if trk.track_id in self._abandoned_emitted:
                continue
            if trk.age_seconds < 30:
                continue
            if trk.is_stationary():
                events.append({
                    "event_type": "abandoned_object",
                    "track_id": trk.track_id,
                    "label": trk.label,
                    "stationary_seconds": trk.age_seconds,
                    "centroid": list(trk.centroid),
                })
                self._abandoned_emitted.add(trk.track_id)
        return events
