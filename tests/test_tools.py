from coolroute.fortyguard import MockFortyGuardClient
from coolroute.tools import ToolRegistry, tool_schemas

DATE = "2024-07-15"


def test_schemas_are_well_formed():
    schemas = tool_schemas()
    names = set()
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        names.add(fn["name"])
    assert {"get_point_conditions", "find_coolest_hour", "evaluate_routes",
            "get_area_heat_snapshot", "get_street_shade"} <= names


def test_dispatch_each_tool():
    reg = ToolRegistry(MockFortyGuardClient())
    assert reg.dispatch("get_point_conditions",
                        {"latitude": 28.61, "longitude": 77.21, "date": DATE, "hour": 14})["source"] == "mock"
    assert reg.dispatch("find_coolest_hour",
                        {"latitude": 28.61, "longitude": 77.21, "date": DATE,
                         "candidate_hours": [6, 12, 18]})["coolest"]["start_hour"] == 6
    routes = [{"name": "a", "waypoints": [[24.49, 54.37], [24.48, 54.36]]},
              {"name": "b", "waypoints": [[24.49, 54.37], [24.50, 54.38]]}]
    assert reg.dispatch("evaluate_routes", {"routes": routes, "date": DATE, "hour": 14})["coolest_route"]
    assert reg.dispatch("get_area_heat_snapshot",
                        {"latitude": 24.49, "longitude": 54.37, "date": DATE, "hour": 14})["summary"]
    assert reg.dispatch("get_street_shade", {"latitude": 24.49, "longitude": 54.37})["source"] == "mock"


def test_unknown_tool_raises():
    reg = ToolRegistry(MockFortyGuardClient())
    try:
        reg.dispatch("nope", {})
        assert False, "expected KeyError"
    except KeyError:
        pass
