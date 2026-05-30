"""Parking-slot occupancy detection.

A "parking slot" is just a polygon Zone of kind ``parking_slot``. We classify
its current state by looking at which (vehicle) tracks have their centroid
inside the polygon:

- **FREE**: no vehicle centroid inside.
- **OCCUPIED**: at least one vehicle centroid inside, within configured
  duration limits.
- **ILLEGAL**: vehicle has been parked for longer than
  ``zone.config["max_duration_seconds"]`` (if set), OR the slot has
  ``zone.config["illegal_when"] == "always"``.

State transitions emit ``DetectionEvent`` rows so the rules engine can fire
the matching ``AlertRule``s the operator configured.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable

from .analytics import ZoneConfig
from .tracking import Track
from .zones import point_in_polygon, polygon_pairs

VEHICLE_LABELS = {"car", "truck", "bus", "motorcycle", "bicycle", "vehicle"}


@dataclass
class SlotSnapshot:
    zone_id: str
    state: str  # 'FREE' | 'OCCUPIED' | 'ILLEGAL'
    since: float
    vehicle_track_id: int | None = None


@dataclass
class ParkingMonitor:
    _state: dict[str, SlotSnapshot] = field(default_factory=dict)

    def update(self, tracks: Iterable[Track], slot_zones: Iterable[ZoneConfig]) -> tuple[
        list[SlotSnapshot], list[dict]
    ]:
        now = time.time()
        vehicle_tracks = [t for t in tracks if t.label in VEHICLE_LABELS]
        events: list[dict] = []
        snapshots: list[SlotSnapshot] = []

        for z in slot_zones:
            polygon = polygon_pairs(z.geometry)
            if len(polygon) < 3:
                continue
            occupant: Track | None = None
            for t in vehicle_tracks:
                if point_in_polygon(t.centroid, polygon):
                    occupant = t
                    break

            prev = self._state.get(z.id)
            max_duration = float(z.config.get("max_duration_seconds") or 0)
            always_illegal = z.config.get("illegal_when") == "always"

            if occupant is None:
                new_state = "free"
                vid = None
                since = now if (prev is None or prev.state != "free") else prev.since
            else:
                # Default OCCUPIED, escalate to ILLEGAL based on rules.
                new_state = "occupied"
                vid = occupant.track_id
                since = (
                    now
                    if (prev is None or prev.state == "free" or prev.vehicle_track_id != vid)
                    else prev.since
                )
                if always_illegal:
                    new_state = "illegal"
                elif max_duration and (now - since) > max_duration:
                    new_state = "illegal"

            snap = SlotSnapshot(zone_id=z.id, state=new_state, since=since, vehicle_track_id=vid)
            snapshots.append(snap)
            self._state[z.id] = snap

            if prev is None or prev.state != new_state:
                event_type = {
                    "free": "parking_vacated",
                    "occupied": "parking_occupied",
                    "illegal": "parking_illegal",
                }[new_state]
                events.append({
                    "event_type": event_type,
                    "zone_id": z.id,
                    "vehicle_track_id": vid,
                    "duration_seconds": (now - since) if new_state != "free" else None,
                })
            elif new_state == "occupied" and max_duration and (now - since) > max_duration * 0.95:
                # Approaching the limit — emit a duration event (idempotent
                # because the alerts engine de-duplicates by event_type+zone).
                events.append({
                    "event_type": "parking_duration",
                    "zone_id": z.id,
                    "vehicle_track_id": vid,
                    "duration_seconds": now - since,
                })

        return snapshots, events
