from coolroute.geo import (
    Route,
    bbox_around,
    haversine_m,
    polygon_from_bbox,
    sample_polyline,
)


def test_haversine_known_distance():
    # ~1 deg of latitude is about 111 km.
    d = haversine_m((0.0, 0.0), (1.0, 0.0))
    assert 110_000 < d < 112_000


def test_sample_polyline_count_and_endpoints():
    wps = [(0.0, 0.0), (0.0, 1.0)]
    pts = sample_polyline(wps, 5)
    assert len(pts) == 5
    assert pts[0] == wps[0] and pts[-1] == wps[-1]
    # evenly spaced longitudes on a straight east-west line
    lons = [p[1] for p in pts]
    assert lons == sorted(lons)


def test_route_length_positive():
    r = Route("x", [(24.49, 54.37), (24.48, 54.36)])
    assert r.length_m() > 0


def test_bbox_helpers_produce_closed_polygon():
    poly = polygon_from_bbox(-1, -1, 1, 1)
    ring = poly["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]  # closed
    assert len(ring) == 5
    around = bbox_around(24.49, 54.37, 0.01)
    assert around["type"] == "FeatureCollection"
