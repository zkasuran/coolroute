"""Planner: heat-aware analyses grounded in FortyGuard data.

Each function calls the adapter (mock or live) and returns a compact,
JSON-serialisable result. These are the deterministic core the agent orchestrates
and explains; the numbers come from the API, not the language model.

`reference_temp` is the coarse input air temperature the API downscales from
(env_params and heat_intelligence require it). The mock models its own field and
ignores it; the live API uses it as the reference reading.
"""
from __future__ import annotations

from typing import Any

from .fortyguard.base import FILTER_RANGE_OF_HOURS, FILTER_SINGLE_HOUR, FortyGuardClient, FortyGuardError
from .fortyguard.heatmodel import heat_risk_band
from .geo import Route, bbox_of_points, haversine_m, sample_polyline

DEFAULT_REFERENCE_TEMP = 35.0


def _first(values: list[Any]) -> Any:
    return values[0] if values else None


def point_conditions(client: FortyGuardClient, latitude: float, longitude: float,
                     date: str, hour: int, reference_temp: float = DEFAULT_REFERENCE_TEMP) -> dict[str, Any]:
    """Feels-like conditions at one point and hour."""
    resp = client.env_params(
        latitude, longitude, reference_temp,
        {"start_date": date, "start_time": f"{hour:02d}:00", "filter_type": FILTER_SINGLE_HOUR},
    )
    p = resp["locations"][0]["parameters"]
    feels = _first(p.get("apparent_temperature_celsius") or p.get("heat_index_celsius", []))
    return {
        "latitude": latitude, "longitude": longitude, "date": date, "hour": hour,
        "air_temperature_celsius": _first(p.get("air_temperature_celsius", [])),
        "feels_like_celsius": feels,
        "wet_bulb_celsius": _first(p.get("wet_bulb_temperature_celsius", [])),
        "relative_humidity_percent": _first(p.get("relative_humidity_percent", [])),
        "heat_risk_band": heat_risk_band(feels) if feels is not None else None,
        "source": resp.get("source", "live"),
    }


def find_coolest_hour(client: FortyGuardClient, latitude: float, longitude: float, date: str,
                      candidate_hours: list[int], duration_hours: int = 1,
                      reference_temp: float = DEFAULT_REFERENCE_TEMP) -> dict[str, Any]:
    """Rank candidate start hours by average feels-like over the task window."""
    duration_hours = max(1, int(duration_hours))
    lo = min(candidate_hours)
    hi = max(candidate_hours) + duration_hours - 1
    resp = client.env_params(
        latitude, longitude, reference_temp,
        {"start_date": date, "start_time": f"{lo:02d}:00", "end_time": f"{hi:02d}:00",
         "filter_type": FILTER_RANGE_OF_HOURS},
    )
    params = resp["locations"][0]["parameters"]
    series = params.get("apparent_temperature_celsius") or params.get("heat_index_celsius", [])
    by_hour = {h: series[i] for i, h in enumerate(range(lo, hi + 1)) if i < len(series)}
    ranked = []
    for start in sorted(candidate_hours):
        window = [by_hour[h] for h in range(start, start + duration_hours) if h in by_hour]
        if not window:
            continue
        avg = round(sum(window) / len(window), 2)
        peak = round(max(window), 2)
        ranked.append({
            "start_hour": start, "window_hours": duration_hours,
            "avg_feels_like_celsius": avg, "peak_feels_like_celsius": peak,
            "heat_risk_band": heat_risk_band(peak),
        })
    ranked.sort(key=lambda r: r["avg_feels_like_celsius"])
    return {
        "location": {"latitude": latitude, "longitude": longitude}, "date": date,
        "coolest": ranked[0] if ranked else None, "ranked": ranked,
        "source": resp.get("source", "live"),
    }


def evaluate_routes(client: FortyGuardClient, routes: list[Route], date: str, hour: int,
                    samples: int = 5, reference_temp: float = DEFAULT_REFERENCE_TEMP) -> dict[str, Any]:
    """Score each candidate route by heat exposure at a given hour.

    Resilient to sparse live coverage: a point whose temperature lookup fails is
    skipped, and a point with no street-view imagery is scored with no shade
    (0.0, the conservative assumption for a heat-safety tool) rather than
    aborting the whole route.
    """
    scored = []
    for route in routes:
        pts = sample_polyline(route.waypoints, samples)
        feels_vals, shade_vals = [], []
        shade_hits = 0
        hottest = None
        for lat, lon in pts:
            try:
                cond = point_conditions(client, lat, lon, date, hour, reference_temp)
            except FortyGuardError:
                continue  # no temperature grounding at this point, skip it
            feels = cond["feels_like_celsius"]
            if feels is None:
                continue
            try:
                shade = client.streetview(lat, lon).get("shade_fraction")
            except FortyGuardError:
                shade = None
            if shade is not None:
                shade_hits += 1
            feels_vals.append(feels)
            shade_vals.append(shade if shade is not None else 0.0)
            if hottest is None or feels > hottest["feels_like_celsius"]:
                hottest = {"latitude": lat, "longitude": lon, "feels_like_celsius": feels}
        if not feels_vals:
            scored.append({"route": route.name, "description": route.description,
                           "length_m": round(route.length_m()), "mean_feels_like_celsius": None,
                           "error": "no readings available for this route", "samples": len(pts)})
            continue
        scored.append({
            "route": route.name, "description": route.description,
            "length_m": round(route.length_m()),
            "mean_feels_like_celsius": round(sum(feels_vals) / len(feels_vals), 2),
            "max_feels_like_celsius": round(max(feels_vals), 2),
            "mean_shade_fraction": round(sum(shade_vals) / len(shade_vals), 3),
            "heat_risk_band": heat_risk_band(max(feels_vals)),
            "hottest_point": hottest, "samples": len(feels_vals), "shade_samples": shade_hits,
        })
    scored.sort(key=lambda r: (r["mean_feels_like_celsius"] is None,
                               r["mean_feels_like_celsius"] or 0.0))
    coolest = next((r for r in scored if r.get("mean_feels_like_celsius") is not None), None)
    return {"date": date, "hour": hour, "coolest_route": coolest,
            "ranked": scored, "source": getattr(client, "backend", "live")}


def area_heat_snapshot(client: FortyGuardClient, latitude: float, longitude: float, date: str,
                       hour: int, granularity: int = 80, pad_deg: float = 0.01) -> dict[str, Any]:
    """Heatmap temperature snapshot over a small area around a point."""
    poly = bbox_of_points([(latitude - pad_deg, longitude - pad_deg),
                           (latitude + pad_deg, longitude + pad_deg)], pad_deg=0.0)
    resp = client.heatmap(
        poly, {"start_date": date, "start_time": f"{hour:02d}:00", "filter_type": FILTER_SINGLE_HOUR},
        granularity=granularity)
    return {"center": {"latitude": latitude, "longitude": longitude}, "date": date, "hour": hour,
            "granularity": granularity, "summary": resp.get("summary"), "source": resp.get("source", "live")}
