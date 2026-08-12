"""Tool layer: OpenAI-style function schemas plus a dispatcher bound to a client.

The schemas are what the agent sees; the dispatcher runs the matching planner
function against the FortyGuard adapter and returns a JSON-serialisable result.
"""
from __future__ import annotations

from typing import Any

from . import planner
from .fortyguard.base import FortyGuardClient
from .geo import Route

_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_point_conditions",
            "description": "Hyperlocal 2m feels-like conditions (air temp, heat index, wet-bulb, humidity, heat-risk band) at one point and hour.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "hour": {"type": "integer", "description": "local hour 0-23"},
                },
                "required": ["latitude", "longitude", "date", "hour"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_coolest_hour",
            "description": "Rank candidate start hours by average feels-like over a task window, to pick the coolest time slot for outdoor work.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "candidate_hours": {"type": "array", "items": {"type": "integer"}},
                    "duration_hours": {"type": "integer", "default": 1},
                },
                "required": ["latitude", "longitude", "date", "candidate_hours"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_routes",
            "description": "Score candidate walking routes by heat exposure at a given hour and return the coolest, with distance and shade trade-offs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "routes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "waypoints": {
                                    "type": "array",
                                    "items": {"type": "array", "items": {"type": "number"},
                                              "minItems": 2, "maxItems": 2},
                                    "description": "ordered [latitude, longitude] pairs",
                                },
                            },
                            "required": ["name", "waypoints"],
                        },
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "hour": {"type": "integer"},
                },
                "required": ["routes", "date", "hour"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_area_heat_snapshot",
            "description": "Heatmap temperature snapshot over a small area around a point: hottest cell, coolest cell and mean.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "date": {"type": "string"},
                    "hour": {"type": "integer"},
                    "granularity": {"type": "integer", "enum": [60, 80, 100], "default": 80},
                },
                "required": ["latitude", "longitude", "date", "hour"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_street_shade",
            "description": "Street-level shade context at a point: shade fraction, sky-view factor and dominant surface.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
]


def tool_schemas() -> list[dict[str, Any]]:
    return _TOOL_SCHEMAS


class ToolRegistry:
    """Binds the tool names to planner calls against a specific client."""

    def __init__(self, client: FortyGuardClient):
        self.client = client

    def schemas(self) -> list[dict[str, Any]]:
        return _TOOL_SCHEMAS

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "get_point_conditions":
            return planner.point_conditions(self.client, args["latitude"], args["longitude"],
                                            args["date"], int(args["hour"]))
        if name == "find_coolest_hour":
            return planner.find_coolest_hour(self.client, args["latitude"], args["longitude"],
                                             args["date"], [int(h) for h in args["candidate_hours"]],
                                             int(args.get("duration_hours", 1)))
        if name == "evaluate_routes":
            routes = [Route(r["name"], [tuple(p) for p in r["waypoints"]], r.get("description", ""))
                      for r in args["routes"]]
            return planner.evaluate_routes(self.client, routes, args["date"], int(args["hour"]))
        if name == "get_area_heat_snapshot":
            return planner.area_heat_snapshot(self.client, args["latitude"], args["longitude"],
                                              args["date"], int(args["hour"]),
                                              int(args.get("granularity", 80)))
        if name == "get_street_shade":
            return self.client.streetview(args["latitude"], args["longitude"])
        raise KeyError(f"unknown tool {name!r}")
