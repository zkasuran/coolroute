from coolroute.fortyguard import MockFortyGuardClient
from coolroute.planner import (
    area_heat_snapshot,
    evaluate_routes,
    find_coolest_hour,
    point_conditions,
)
from coolroute.scenarios import ABU_DHABI_ROUTES

DATE = "2024-07-15"


def _client():
    return MockFortyGuardClient()


def test_point_conditions_shape():
    r = point_conditions(_client(), 28.61, 77.21, DATE, 14)
    assert set(("feels_like_celsius", "wet_bulb_celsius", "heat_risk_band")) <= set(r)
    assert r["source"] == "mock"


def test_find_coolest_hour_avoids_midday_and_sorts():
    r = find_coolest_hour(_client(), 28.61, 77.21, DATE, [6, 9, 12, 15, 18], duration_hours=1)
    assert r["coolest"]["start_hour"] == 6  # early morning is coolest on the diurnal curve
    avgs = [x["avg_feels_like_celsius"] for x in r["ranked"]]
    assert avgs == sorted(avgs)
    # midday must not win
    assert r["coolest"]["start_hour"] != 15


def test_find_coolest_hour_deterministic():
    a = find_coolest_hour(_client(), 28.61, 77.21, DATE, [7, 12, 17], 2)
    b = find_coolest_hour(_client(), 28.61, 77.21, DATE, [7, 12, 17], 2)
    assert a == b


def test_evaluate_routes_ranks_and_picks_coolest():
    r = evaluate_routes(_client(), ABU_DHABI_ROUTES, DATE, 14, samples=5)
    assert len(r["ranked"]) == 3
    means = [x["mean_feels_like_celsius"] for x in r["ranked"]]
    assert means == sorted(means)
    assert r["coolest_route"]["route"] == r["ranked"][0]["route"]
    # every route carries a distance and a shade figure
    for row in r["ranked"]:
        assert row["length_m"] > 0
        assert 0.0 <= row["mean_shade_fraction"] <= 1.0


def test_area_heat_snapshot_summary():
    r = area_heat_snapshot(_client(), 24.49, 54.37, DATE, 14, granularity=100)
    assert r["summary"]["min"] <= r["summary"]["max"]
    assert r["source"] == "mock"
