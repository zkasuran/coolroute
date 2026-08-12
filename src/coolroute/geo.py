"""Geometry helpers: distances, route sampling and GeoJSON for the heatmap AOI."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]  # (latitude, longitude)


@dataclass
class Route:
    name: str
    waypoints: list[Point]
    description: str = ""

    def length_m(self) -> float:
        return sum(
            haversine_m(a, b) for a, b in zip(self.waypoints, self.waypoints[1:])
        )


def haversine_m(a: Point, b: Point) -> float:
    """Great-circle distance between two (lat, lon) points, in metres."""
    r = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def sample_polyline(waypoints: list[Point], n: int) -> list[Point]:
    """Return n points spread evenly along a polyline by arc length."""
    if n < 2 or len(waypoints) < 2:
        return list(waypoints)
    segs = list(zip(waypoints, waypoints[1:]))
    lengths = [haversine_m(a, b) for a, b in segs]
    total = sum(lengths) or 1.0
    out: list[Point] = [waypoints[0]]
    for i in range(1, n - 1):
        target = total * i / (n - 1)
        acc = 0.0
        for (a, b), seg_len in zip(segs, lengths):
            if acc + seg_len >= target:
                t = (target - acc) / (seg_len or 1.0)
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                break
            acc += seg_len
    out.append(waypoints[-1])
    return out


def polygon_from_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict[str, Any]:
    ring = [
        [min_lon, min_lat], [max_lon, min_lat],
        [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat],
    ]
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}


def bbox_around(lat: float, lon: float, pad_deg: float = 0.01) -> dict[str, Any]:
    return polygon_from_bbox(lon - pad_deg, lat - pad_deg, lon + pad_deg, lat + pad_deg)


def bbox_of_points(points: list[Point], pad_deg: float = 0.002) -> dict[str, Any]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return polygon_from_bbox(min(lons) - pad_deg, min(lats) - pad_deg,
                             max(lons) + pad_deg, max(lats) + pad_deg)
