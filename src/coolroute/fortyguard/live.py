"""Live backend: real HTTP against the FortyGuard Temperature API.

Faithful to the documented contract: every call is a POST with the key in the
`api-key` header (status is a GET). Submissions return an activity_id and the
final payload is polled from GET /v1/status/{activity_id}; if a submission comes
back already resolved, that payload is used directly.

Swap this in with one line of config: set FORTYGUARD_BACKEND=live and provide
FORTYGUARD_API_KEY. No call site above the adapter changes.

Note: the request bodies and the `api-key` header are confirmed from the public
docs and the live 401 body. The submit-then-poll timing is implemented to the
documented async description; confirm the exact status field values against a
real key at integration time (see docs/fortyguard-api-usage.md).
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from .base import ANALYTIC_TCM, DEFAULT_BASE_URL, FortyGuardError

_TERMINAL_OK = {"completed", "complete", "success", "succeeded", "done"}
_TERMINAL_BAD = {"failed", "error", "cancelled"}


class LiveFortyGuardClient:
    backend = "live"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 client: httpx.Client | None = None, poll_interval: float = 1.0,
                 max_polls: int = 60):
        if not api_key:
            raise FortyGuardError(401, "Missing required 'api-key'. Set FORTYGUARD_API_KEY.")
        self._base = base_url.rstrip("/")
        self._headers = {"api-key": api_key, "content-type": "application/json"}
        self._client = client or httpx.Client(timeout=30.0)
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

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post(f"{self._base}/{path}", json=payload, headers=self._headers)
        return self._raise_for_body(resp)

    def _get(self, path: str) -> dict[str, Any]:
        resp = self._client.get(f"{self._base}/{path}", headers=self._headers)
        return self._raise_for_body(resp)

    def _submit_and_wait(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._post(path, payload)
        status = str(body.get("status", "")).lower()
        if status in _TERMINAL_OK or "locations" in body or "cells" in body or "summary" in body:
            return body
        activity_id = body.get("activity_id")
        if not activity_id:
            return body  # already the result, no async id issued
        for _ in range(self._max_polls):
            time.sleep(self._poll_interval)
            result = self.status(activity_id)
            st = str(result.get("status", "")).lower()
            if st in _TERMINAL_OK:
                return result
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
        return self._submit_and_wait("heat_intelligence", {
            "latitude": latitude, "longitude": longitude, "temperature": temperature,
            "date": date, "analysis": analysis or ["environmental"],
        })

    def heatmap(self, polygon_aoi, date_time, granularity=80, analytic_type=ANALYTIC_TCM,
                threshold=30.0, direction="above"):
        return self._submit_and_wait("heatmap", {
            "polygon_aoi": polygon_aoi, "date_time": date_time, "granularity": granularity,
            "analytic_type": analytic_type, "threshold": threshold, "direction": direction,
        })

    def satellite(self, latitude, longitude, date_time, granularity=80):
        return self._submit_and_wait("satellite", {
            "sat": {"latitude": latitude, "longitude": longitude},
            "date_time": date_time, "granularity": granularity,
        })

    def streetview(self, latitude, longitude, vertical_angle=10.0, horizontal_angle=90.0, back_view=False):
        return self._submit_and_wait("streetview", {
            "latitude": latitude, "longitude": longitude, "vertical_angle": vertical_angle,
            "horizontal_angle": horizontal_angle, "back_view": back_view,
        })

    def status(self, activity_id):
        return self._get(f"status/{activity_id}")
