"""FortyGuard Temperature API adapter: shared contract, constants, errors.

Endpoint surface, request shapes and the `api-key` header are taken from the
public API docs at docs-api.fortyguard.com and the live 401 error body. All
endpoints are POST with a JSON body except status, which is GET. Submissions
return an activity_id; the final result is polled from GET /v1/status/{id}.

Documented data window: start_date must fall between 2019-01-01 and 12 hours
past the current time. The API forecasts at most ~12 hours ahead.
"""
from __future__ import annotations

from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Protocol

API_VERSION = "v1"
DEFAULT_BASE_URL = "https://api.fortyguard.com/v1"

# Spatial resolution options for heatmap / satellite tiles, in metres.
GRANULARITIES = (60, 80, 100)

# date_time.filter_type meanings (from the docs).
FILTER_SINGLE_HOUR = 1  # start_date + start_time
FILTER_RANGE_OF_HOURS = 2  # start_date + start_time + end_time (same day)
FILTER_SINGLE_DAY = 3  # start_date
FILTER_DATE_RANGE = 4  # start_date + end_date

# heatmap analytic_type options.
ANALYTIC_TCM = "tcm"  # temperature snapshot, degrees C per tile
ANALYTIC_TIME_OF_MEASURE = "time_of_measure"  # hour of day the tile peaks
ANALYTIC_PERSISTENCE = "persistence"  # longest run of hours past threshold

DATA_FLOOR = _date(2019, 1, 1)
FORECAST_HORIZON_HOURS = 12


class FortyGuardError(Exception):
    """Mirrors the API error body: {"error": true, "status_code": N, "details": {...}}."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{status_code}] {message}")

    def as_body(self) -> dict[str, Any]:
        return {
            "error": True,
            "status_code": self.status_code,
            "details": {"message": self.message},
        }


def _parse_date(value: str) -> _date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise FortyGuardError(400, f"Invalid date {value!r}, expected YYYY-MM-DD.") from exc


def validate_window(start_date: str, start_time: str | None = None) -> None:
    """Enforce the documented 2019-floor and ~12h forecast ceiling.

    Failed validation matches the real API: it rejects the call (and, per the
    FAQ, a rejected call does not consume credits).
    """
    d = _parse_date(start_date)
    if d < DATA_FLOOR:
        raise FortyGuardError(422, "start_date earlier than 2019-01-01 is not supported.")
    now = datetime.now(timezone.utc)
    when = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if start_time:
        try:
            hh, mm = (int(x) for x in start_time.split(":"))
            when = when.replace(hour=hh, minute=mm)
        except ValueError as exc:
            raise FortyGuardError(400, f"Invalid start_time {start_time!r}, expected HH:MM.") from exc
    if when > now + timedelta(hours=FORECAST_HORIZON_HOURS):
        raise FortyGuardError(
            422, "Requests more than 12 hours in the future are not supported."
        )


class FortyGuardClient(Protocol):
    """The adapter contract. Mock and live backends both implement this."""

    backend: str

    def env_params(
        self,
        latitude: float,
        longitude: float,
        temperature: float,
        date_time: dict[str, Any],
        parameters: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def heat_intelligence(
        self,
        latitude: float,
        longitude: float,
        temperature: float,
        date: str,
        analysis: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def heatmap(
        self,
        polygon_aoi: dict[str, Any],
        date_time: dict[str, Any],
        granularity: int = 80,
        analytic_type: str = ANALYTIC_TCM,
        threshold: float = 30.0,
        direction: str = "above",
    ) -> dict[str, Any]: ...

    def streetview(
        self,
        latitude: float,
        longitude: float,
        vertical_angle: float = 10.0,
        horizontal_angle: float = 90.0,
        back_view: bool = False,
    ) -> dict[str, Any]: ...

    def status(self, activity_id: str) -> dict[str, Any]: ...
