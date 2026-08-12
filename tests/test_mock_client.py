import pytest

from coolroute.fortyguard import MockFortyGuardClient
from coolroute.fortyguard.base import (
    ANALYTIC_TCM,
    FILTER_RANGE_OF_HOURS,
    FILTER_SINGLE_HOUR,
    FortyGuardError,
)

DATE = "2024-07-15"


@pytest.fixture
def client():
    return MockFortyGuardClient()


def test_env_params_shape_and_mock_tag(client):
    r = client.env_params(28.61, 77.21, 35.0,
                          {"start_date": DATE, "start_time": "14:00", "filter_type": FILTER_SINGLE_HOUR})
    assert r["source"] == "mock"
    assert "notice" in r
    loc = r["locations"][0]
    p = loc["parameters"]
    for key in ("air_temperature_celsius", "heat_index_celsius", "wet_bulb_temperature_celsius",
                "relative_humidity_percent"):
        assert isinstance(p[key], list) and len(p[key]) == 1
    assert "solar_irradiance" in loc
    assert r["metadata"]["timestamps"] == [f"{DATE}T14:00:00Z"]


def test_env_params_range_returns_time_aligned_arrays(client):
    r = client.env_params(28.61, 77.21, 35.0,
                          {"start_date": DATE, "start_time": "09:00", "end_time": "17:00",
                           "filter_type": FILTER_RANGE_OF_HOURS})
    hours = list(range(9, 18))
    assert len(r["locations"][0]["parameters"]["air_temperature_celsius"]) == len(hours)
    assert len(r["metadata"]["timestamps"]) == len(hours)


def test_env_params_is_deterministic(client):
    args = (28.61, 77.21, 35.0, {"start_date": DATE, "start_time": "14:00", "filter_type": 1})
    assert client.env_params(*args) == client.env_params(*args)


def test_parameter_selection_filters(client):
    r = client.env_params(28.61, 77.21, 35.0,
                          {"start_date": DATE, "start_time": "14:00", "filter_type": 1},
                          parameters=["heat_index_celsius"])
    keys = set(r["locations"][0]["parameters"])
    assert keys == {"heat_index_celsius"}


def test_forecast_cap_rejected(client):
    with pytest.raises(FortyGuardError) as exc:
        client.env_params(28.61, 77.21, 35.0,
                          {"start_date": "2099-01-01", "start_time": "12:00", "filter_type": 1})
    assert exc.value.status_code == 422


def test_data_floor_rejected(client):
    with pytest.raises(FortyGuardError):
        client.env_params(28.61, 77.21, 35.0,
                          {"start_date": "2018-12-31", "start_time": "12:00", "filter_type": 1})


def test_error_body_matches_api_contract():
    err = FortyGuardError(401, "Missing required 'api-key' header.")
    body = err.as_body()
    assert body["error"] is True
    assert body["status_code"] == 401
    assert "message" in body["details"]


def test_heatmap_summary_has_hottest_and_coolest(client):
    from coolroute.geo import bbox_around
    r = client.heatmap(bbox_around(24.49, 54.37, 0.01),
                       {"start_date": DATE, "start_time": "14:00", "filter_type": 1},
                       granularity=100, analytic_type=ANALYTIC_TCM)
    s = r["summary"]
    assert s["cell_count"] >= 1
    assert s["min"] <= s["mean"] <= s["max"]
    assert s["hottest_cell"]["value"] == s["max"]
    assert s["coolest_cell"]["value"] == s["min"]
    assert r["source"] == "mock"


def test_streetview_and_status(client):
    sv = client.streetview(24.49, 54.37)
    assert 0.0 <= sv["shade_fraction"] <= 1.0
    assert sv["dominant_surface"] in ("vegetation", "paved", "mixed")
    st = client.status("heatmap_abc123")
    assert st["status"] == "completed" and st["source"] == "mock"
