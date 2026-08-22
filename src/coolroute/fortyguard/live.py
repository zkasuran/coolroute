"""Live backend: real HTTP against the FortyGuard Temperature API.

Verified against a real hackathon key on 2026-08-18. Every data call is a POST
with the key in the `api-key` header; the result is polled from
GET /v1/status/{activity_id}. The API wraps every response in an envelope:

    {"error": false, "status_code": 200, "message": "...",
     "data": {"activity_id": "...", "status": "Completed", "result": {...}}}

so a submission returns `data.activity_id`, and the poll returns `data.status`
plus `data.result`. The real per-endpoint result shapes differ from the mock's
documented-guess shapes, so this client normalises each one back to the internal
shape the planner consumes (the same shape the mock returns): env_params keeps
`locations[].parameters`, streetview is reduced to a shade fraction from the
street segmentation, and heatmap is reduced to a summary over its cells.

Swap this in with one line of config: set FORTYGUARD_BACKEND=live and provide
FORTYGUARD_API_KEY. No call site above the adapter changes.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from .base import ANALYTIC_TCM, DEFAULT_BASE_URL, FortyGuardError

_TERMINAL_OK = {"completed", "complete", "success", "succeeded", "done"}
_TERMINAL_BAD = {"failed", "error", "cancelled"}

# street-segmentation labels that cast or represent shade vs. open sky vs. ground
_SHADE_LABELS = ("building", "tree", "fence", "wall", "hedge", "awning", "bridge")
_VEG_LABELS = ("tree", "grass", "plant", "vegetation", "earth, ground")
_PAVED_LABELS = ("road", "road, route", "sidewalk", "pavement", "footpath")


class LiveFortyGuardClient:
    backend = "live"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 client: httpx.Client | None = None, poll_interval: float = 0.6,
                 max_polls: int = 90):
        if not api_key:
            raise FortyGuardError(401, "Missing required 'api-key'. Set FORTYGUARD_API_KEY.")
        self._base = base_url.rstrip("/")
        self._headers = {"api-key": api_key, "content-type": "application/json"}
        self._client = client or httpx.Client(timeout=60.0)
        self._poll_interval = poll_interval
        self._max_polls = max_polls

    # --- low-level ---
    def _raise_for_body(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            body = resp.json()
        except ValueError:
            raise FortyGuardError(resp.status_code, resp.text[:200] or "non-JSON response")
        if isinstance(body, dict) and body.get("error"):
            msg = body.get("details", {}).get("message", "request failed")
            raise FortyGuardError(body.get("status_code", resp.status_code), msg)
        if resp.status_code >= 400:
            raise FortyGuardError(resp.status_code, str(body)[:200])
        return body

    @staticmethod
    def _data(env: dict[str, Any]) -> dict[str, Any]:
        """Unwrap the `data` envelope; tolerate an already-unwrapped body."""
        if isinstance(env, dict) and isinstance(env.get("data"), dict):
            return env["data"]
        return env

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post(f"{self._base}/{path}", json=payload, headers=self._headers)
        return self._raise_for_body(resp)

    def _get(self, path: str) -> dict[str, Any]:
        resp = self._client.get(f"{self._base}/{path}", headers=self._headers)
        return self._raise_for_body(resp)

    def _submit_and_wait(self, path: str, payload: dict[str, Any],
                         max_polls: int | None = None) -> dict[str, Any]:
        data = self._data(self._post(path, payload))
        if "result" in data:                       # already resolved
            return data["result"]
        if str(data.get("status", "")).lower() in _TERMINAL_OK:
            return data.get("result", data)
        activity_id = data.get("activity_id")
        if not activity_id:
            return data                            # synchronous body, no async id
        for _ in range(max_polls or self._max_polls):
            time.sleep(self._poll_interval)
            sd = self.status(activity_id)
            st = str(sd.get("status", "")).lower()
            if st in _TERMINAL_OK:
                return sd.get("result", sd)
            if st in _TERMINAL_BAD:
                raise FortyGuardError(502, f"activity {activity_id} {st}")
        raise FortyGuardError(504, f"activity {activity_id} did not complete in time")

    # --- documented endpoints ---
    def env_params(self, latitude, longitude, temperature, date_time, parameters=None):
        payload: dict[str, Any] = {
            "latitude": latitude, "longitude": longitude,
            "temperature": temperature, "date_time": date_time,
        }
        if parameters:
            payload["parameters"] = parameters
        return self._submit_and_wait("env_params", payload)

    def heat_intelligence(self, latitude, longitude, temperature, date, analysis=None):
        # The live endpoint returns a download_link to a report rather than inline
        # figures; the agent's risk band is derived from env_params felt temperature.
        result = self._submit_and_wait("heat_intelligence", {
            "latitude": latitude, "longitude": longitude, "temperature": temperature,
            "date": date, "analysis": analysis or ["environmental"],
        })
        return {"source": "live", **(result if isinstance(result, dict) else {"result": result})}

    def heatmap(self, polygon_aoi, date_time, granularity=80, analytic_type=ANALYTIC_TCM,
                threshold=30.0, direction="above"):
        result = self._submit_and_wait("heatmap", {
            "polygon_aoi": polygon_aoi, "date_time": date_time, "granularity": granularity,
            "analytic_type": analytic_type, "threshold": threshold, "direction": direction,
        })
        return self._heatmap_summary(result, analytic_type, granularity)

    def satellite(self, latitude, longitude, date_time, granularity=80):
        result = self._submit_and_wait("satellite", {
            "sat": {"latitude": latitude, "longitude": longitude},
            "date_time": date_time, "granularity": granularity,
        })
        seg = (result.get("segmentation") or {}) if isinstance(result, dict) else {}
        return {  # drop the base64 image blobs, keep the land-cover breakdown
            "source": "live",
            "coordinates": result.get("coordinates") if isinstance(result, dict) else None,
            "image_year": result.get("image_year") if isinstance(result, dict) else None,
            "segments": seg.get("segments"),
        }

    def streetview(self, latitude, longitude, vertical_angle=10.0, horizontal_angle=90.0, back_view=False):
        # Shade is auxiliary and street-view coverage is sparse and sometimes slow
        # to resolve, so cap the wait: a point that does not resolve quickly is
        # treated by the route planner as having no shade rather than stalling it.
        result = self._submit_and_wait("streetview", {
            "latitude": latitude, "longitude": longitude, "vertical_angle": vertical_angle,
            "horizontal_angle": horizontal_angle, "back_view": back_view,
        }, max_polls=10)
        return self._street_shade(result)

    def status(self, activity_id):
        return self._data(self._get(f"status/{activity_id}"))

    # --- normalisers: real API result -> internal shape the planner consumes ---
    @staticmethod
    def _street_shade(result: dict[str, Any]) -> dict[str, Any]:
        front = (result.get("front") or {}) if isinstance(result, dict) else {}
        seg = front.get("segments") or {}
        out: dict[str, Any] = {
            "source": "live",
            "coordinates": result.get("coordinates") if isinstance(result, dict) else None,
            "image_date": front.get("image_date"),
            "segments": seg or None,
        }
        total = sum(v for v in seg.values() if isinstance(v, (int, float)))
        if not total:
            out.update(shade_fraction=None, sky_view_factor=None, dominant_surface=None)
            return out
        frac = lambda names: sum(seg.get(n, 0.0) for n in names) / total
        out["shade_fraction"] = round(min(1.0, frac(_SHADE_LABELS)), 3)
        out["sky_view_factor"] = round(frac(("sky",)), 3)
        ground = {"vegetation": frac(_VEG_LABELS), "paved": frac(_PAVED_LABELS)}
        out["dominant_surface"] = (max(ground, key=ground.get)
                                   if max(ground.values()) >= 0.3 else "mixed")
        return out

    @staticmethod
    def _heatmap_summary(result: dict[str, Any], analytic_type: str, granularity: int) -> dict[str, Any]:
        features = ((result.get("map_data") or {}).get("features") or []) if isinstance(result, dict) else []
        cells: list[dict[str, Any]] = []
        for f in features:
            props = f.get("properties") or {}
            value = props.get("value", props.get("temperature", props.get(analytic_type)))
            lat, lon = _feature_centroid(f.get("geometry") or {})
            if value is not None:
                cells.append({"latitude": lat, "longitude": lon, "value": value})
        base = {"source": "live", "analytic_type": analytic_type, "granularity": granularity, "cells": cells}
        if cells:
            values = [c["value"] for c in cells]
            base["summary"] = {
                "cell_count": len(cells), "min": min(values), "max": max(values),
                "mean": round(sum(values) / len(values), 2),
                "hottest_cell": max(cells, key=lambda c: c["value"]),
                "coolest_cell": min(cells, key=lambda c: c["value"]),
            }
        else:
            n = (result.get("stats_data") or {}).get("n_cells", 0) if isinstance(result, dict) else 0
            base["summary"] = {"cell_count": n, "min": None, "max": None, "mean": None,
                               "hottest_cell": None, "coolest_cell": None,
                               "note": "no cells returned for this area and time window"}
        return base


def _feature_centroid(geometry: dict[str, Any]) -> tuple[float | None, float | None]:
    coords = geometry.get("coordinates")
    pts: list[list[float]] = []
    def walk(c):
        if isinstance(c, list) and c and isinstance(c[0], (int, float)) and len(c) >= 2:
            pts.append(c)
        elif isinstance(c, list):
            for x in c:
                walk(x)
    walk(coords)
    if not pts:
        return None, None
    return round(sum(p[1] for p in pts) / len(pts), 5), round(sum(p[0] for p in pts) / len(pts), 5)
