"""Contract test for the live backend using an httpx MockTransport.

The fake responses mirror the real FortyGuard envelope verified against a live
key on 2026-08-18: every call returns {"error", "status_code", "message",
"data": {...}}, a submission carries data.activity_id, and the poll of
GET /v1/status/{id} carries data.status ("Completed") and data.result. The
per-endpoint result shapes are the real ones, and the tests assert that the live
client normalises them into the internal shape the planner consumes.
"""
import json

import httpx
import pytest

from coolroute.fortyguard.base import FortyGuardError
from coolroute.fortyguard.live import LiveFortyGuardClient

BASE = "https://api.fortyguard.com/v1"
KEY = "test-key-123"


def make_client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return LiveFortyGuardClient(api_key=KEY, base_url=BASE, client=http, poll_interval=0.0)


def _envelope(data, message=""):
    return {"error": False, "status_code": 200, "message": message, "data": data}


def submit_poll_handler(result, seen=None, activity_id="act-1"):
    """POST -> data.activity_id; GET /status/{id} -> data.status Completed + result."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            if seen is not None:
                seen["path"] = request.url.path
                seen["api_key"] = request.headers.get("api-key")
                seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_envelope({"activity_id": activity_id}, "Submitted"))
        assert request.url.path == f"/v1/status/{activity_id}"
        return httpx.Response(200, json=_envelope(
            {"activity_id": activity_id, "status": "Completed", "result": result}, "Completed"))
    return handler


def test_env_params_request_shape_and_async_unwrap():
    seen = {}
    result = {
        "metadata": {"timezone": "GMT+4", "timestamps": ["2024-07-15T14:00:00+04:00"]},
        "locations": [{"lat": 40.7128, "lon": -74.006, "elevation": 5.0, "temperature": 32.5,
                       "parameters": {"heat_index_celsius": [41.2],
                                      "apparent_temperature_celsius": [38.9]}}],
    }
    client = make_client(submit_poll_handler(result, seen))
    r = client.env_params(40.7128, -74.006, 32.5,
                          {"start_date": "2024-07-15", "start_time": "14:00", "filter_type": 1})
    assert seen["path"] == "/v1/env_params"
    assert seen["api_key"] == KEY
    assert seen["body"]["temperature"] == 32.5
    assert seen["body"]["date_time"]["filter_type"] == 1
    # the client returns data.result directly: the planner reads locations[].parameters
    assert r["locations"][0]["parameters"]["heat_index_celsius"] == [41.2]
    assert r["locations"][0]["parameters"]["apparent_temperature_celsius"] == [38.9]


def test_streetview_segmentation_becomes_shade_fraction():
    # real streetview result: front.segments are percentage land-cover labels
    result = {"coordinates": {"latitude": "24.4539", "longitude": "54.3773"},
              "front": {"segments": {"building": 20.0, "sky": 15.0, "tree": 10.0, "grass": 5.0,
                                     "road": 45.0, "fence": 5.0, "others": 0.0},
                        "image_date": "2022-03-01"}}
    client = make_client(submit_poll_handler(result))
    sv = client.streetview(24.4539, 54.3773)
    # shade = building + tree + fence = 35% ; sky-view = sky = 15%
    assert sv["shade_fraction"] == 0.35
    assert sv["sky_view_factor"] == 0.15
    assert sv["dominant_surface"] == "paved"  # road 45% dominates vegetation 15%
    assert sv["source"] == "live"


def test_streetview_missing_segments_degrades_cleanly():
    client = make_client(submit_poll_handler({"coordinates": {}, "front": {}}))
    sv = client.streetview(1.0, 2.0)
    assert sv["shade_fraction"] is None and sv["dominant_surface"] is None


def test_heatmap_empty_field_reports_zero_cells():
    # verified real shape when the tier returns no cells for an AOI/window
    result = {"map_data": {"type": "FeatureCollection", "features": []},
              "stats_data": {"activity_id": "act-1", "n_cells": 0}}
    client = make_client(submit_poll_handler(result))
    r = client.heatmap({"type": "FeatureCollection", "features": []},
                       {"start_date": "2024-07-15", "filter_type": 3}, granularity=80)
    assert r["summary"]["cell_count"] == 0
    assert r["summary"]["max"] is None
    assert "no cells" in r["summary"]["note"]


def test_heatmap_populated_field_is_summarised():
    # populated-cell property schema is a documented guess (tier returned none live);
    # this exercises the summary math over map_data features.
    feats = [{"type": "Feature", "properties": {"value": 44.0},
              "geometry": {"type": "Point", "coordinates": [54.38, 24.45]}},
             {"type": "Feature", "properties": {"value": 31.0},
              "geometry": {"type": "Point", "coordinates": [54.39, 24.46]}}]
    result = {"map_data": {"type": "FeatureCollection", "features": feats},
              "stats_data": {"activity_id": "act-1", "n_cells": 2}}
    client = make_client(submit_poll_handler(result))
    r = client.heatmap({"type": "FeatureCollection", "features": []},
                       {"start_date": "2024-07-15", "filter_type": 3})
    assert r["summary"]["cell_count"] == 2
    assert r["summary"]["min"] == 31.0 and r["summary"]["max"] == 44.0
    assert r["summary"]["hottest_cell"]["value"] == 44.0


def test_error_body_becomes_fortyguard_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": True, "status_code": 401,
                                         "details": {"message": "Missing required 'api-key' header."}})

    client = make_client(handler)
    with pytest.raises(FortyGuardError) as exc:
        client.env_params(1.0, 2.0, 30.0, {"start_date": "2024-07-15", "start_time": "10:00", "filter_type": 1})
    assert exc.value.status_code == 401
    assert "api-key" in exc.value.message


def test_missing_key_rejected_before_any_call():
    with pytest.raises(FortyGuardError):
        LiveFortyGuardClient(api_key="", base_url=BASE)
