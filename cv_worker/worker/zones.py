"""Zone geometry helpers — point-in-polygon, line crossing, etc.

All input coordinates are normalised to ``[0, 1]`` (same as
``apps.cameras.models.Zone.geometry``). Helpers are pure-Python so the worker
keeps no NumPy dependency beyond what the detector already loads.
"""
from __future__ import annotations

from typing import Sequence

Point = tuple[float, float]


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray-casting algorithm; works for any simple polygon."""
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _ccw(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """True if segment p1-p2 crosses segment p3-p4."""
    d1 = _ccw(p3, p4, p1)
    d2 = _ccw(p3, p4, p2)
    d3 = _ccw(p1, p2, p3)
    d4 = _ccw(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    return False


def line_direction(p1: Point, p2: Point, c1: Point, c2: Point) -> str:
    """Return 'IN' or 'OUT' for a crossing of line p1->p2 by trajectory c1->c2.

    Convention: looking along p1→p2, 'IN' = right-to-left crossing, 'OUT' =
    left-to-right. This is just based on the sign of the cross product so it
    only matters that it is consistent.
    """
    cross = _ccw(p1, p2, c2)
    return "IN" if cross > 0 else "OUT"


def polygon_pairs(geometry: Sequence[Sequence[float]]) -> list[Point]:
    """Normalise a Zone.geometry list into a list of (x, y) tuples."""
    out: list[Point] = []
    for item in geometry:
        if len(item) >= 2:
            out.append((float(item[0]), float(item[1])))
    return out
