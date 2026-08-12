"""Contract test for the live backend using an httpx MockTransport, so the real
request shapes (api-key header, URLs, JSON bodies) and the submit-then-poll flow
are verified without a real API key.
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


def test_env_params_request_shape_and_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["api_key"] = request.headers.get("api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "metadata": {"timezone": "UTC", "timestamps": ["2024-07-15T14:00:00Z"]},
            "locations": [{"latitude": 40.7128, "longitude": -74.006,
                           "parameters": {"heat_index_celsius": [41.2]}}],
        })

    client = make_client(handler)
    r = client.env_params(40.7128, -74.006, 32.5,
                          {"start_date": "2024-07-15", "start_time": "14:00", "filter_type": 1})
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/env_params"
    assert seen["api_key"] == KEY
    assert seen["body"]["latitude"] == 40.7128
    assert seen["body"]["temperature"] == 32.5
    assert seen["body"]["date_time"]["filter_type"] == 1
    assert r["locations"][0]["parameters"]["heat_index_celsius"] == [41.2]


def test_streetview_and_heatmap_bodies():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"status": "completed", "summary": {"min": 30, "max": 40}})

    client = make_client(handler)
    client.streetview(40.7128, -74.006, vertical_angle=10.0, horizontal_angle=90.0, back_view=False)
    client.heatmap({"type": "FeatureCollection", "features": []},
                   {"start_date": "2024-07-15", "filter_type": 3}, granularity=80)
    sv_body = calls[0][1]
    assert calls[0][0] == "/v1/streetview" and sv_body["horizontal_angle"] == 90.0
    hm_path, hm_body = calls[1]
    assert hm_path == "/v1/heatmap" and hm_body["granularity"] == 80
    assert hm_body["analytic_type"] == "tcm"


def test_async_submit_then_poll_status():
    state = {"posted": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            state["posted"] = True
            return httpx.Response(200, json={"activity_id": "heatmap_x1", "status": "processing"})
        # GET /v1/status/heatmap_x1
        assert request.url.path == "/v1/status/heatmap_x1"
        return httpx.Response(200, json={"activity_id": "heatmap_x1", "status": "completed",
                                         "summary": {"min": 31.0, "max": 44.0}})

    client = make_client(handler)
    r = client.heatmap({"type": "FeatureCollection", "features": []},
                       {"start_date": "2024-07-15", "filter_type": 3})
    assert state["posted"]
    assert r["status"] == "completed"
    assert r["summary"]["max"] == 44.0


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
