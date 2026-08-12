"""Canned demo scenarios so the CLI and web UI have something concrete to run.

Coordinates are real city locations; the heat values attached to them at run
time come from the adapter (mock by default, labelled as such).
"""
from __future__ import annotations

from .geo import Route

# Three ways to walk roughly the same corridor in Abu Dhabi: a bare arterial, a
# waterfront path and a park-and-back-streets detour. Which is coolest depends on
# the hour and the hyperlocal field, which is the whole point: the agent ranks on
# the data, not on the route names.
ABU_DHABI_ROUTES = [
    Route("Arterial (direct)",
          [(24.4939, 54.3773), (24.4895, 54.3690), (24.4853, 54.3608)],
          "Shortest path along an exposed multi-lane road."),
    Route("Corniche (waterfront)",
          [(24.4939, 54.3773), (24.4760, 54.3600), (24.4853, 54.3608)],
          "Longer waterfront path with a sea breeze."),
    Route("Park detour (green)",
          [(24.4939, 54.3773), (24.4900, 54.3820), (24.4853, 54.3608)],
          "Through a green space with more tree cover, back streets on the far side."),
]

# A delivery rider deciding when to run a block of outdoor drops in Delhi.
DELHI_SHIFT = {
    "latitude": 28.6139, "longitude": 77.2090, "date_hint": "summer afternoon",
    "candidate_hours": [7, 9, 11, 13, 15, 17, 19], "duration_hours": 2,
}

SCENARIOS = {
    "abu-dhabi-route": {
        "kind": "route",
        "question": "I have to walk from the marina area to the museum district around 2pm. Which route stays coolest?",
        "routes": ABU_DHABI_ROUTES, "hour": 14,
    },
    "delhi-shift": {
        "kind": "time",
        "question": "When is the coolest 2-hour window to run my outdoor delivery drops in central Delhi today?",
        **DELHI_SHIFT,
    },
}
