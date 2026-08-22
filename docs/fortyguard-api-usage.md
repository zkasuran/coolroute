# FortyGuard Temperature API usage

How Cool Route Planner uses the FortyGuard Temperature API. The endpoint surface,
the `api-key` header, the async envelope and the per-endpoint response shapes were
verified against a real hackathon key on 2026-08-18. The project talks to the API
only through one adapter (`src/coolroute/fortyguard/`), so the mock and the live
backend are interchangeable: the live client normalises each real response into
the internal shape the planner consumes.

## Basics

- Base URL: `https://api.fortyguard.com/v1`
- Auth: the key goes in the `api-key` request header. A call without it returns
  `401 {"error": true, "status_code": 401, "details": {"message": "..."}}`.
- All data endpoints are `POST` with a JSON body. Status is a `GET`.
- Temperature is 2m above ground, degrees Celsius.
- Data window: `start_date` must fall between 2019-01-01 and about 12 hours past
  the current time. Our adapter enforces this before the call (`validate_window`),
  matching the API, which rejects out-of-window requests (and per the FAQ a
  rejected call costs no credits).

## The async envelope

Every response is wrapped:

```
{"error": false, "status_code": 200, "message": "...",
 "data": {"activity_id": "<uuid>"}}
```

A submission returns `data.activity_id`. Poll `GET /v1/status/{activity_id}` until
`data.status` is `"Completed"`, then read `data.result`:

```
{"error": false, "status_code": 200, "message": "Completed",
 "data": {"activity_id": "<uuid>", "status": "Completed", "result": { ... }}}
```

The live client unwraps `data`, polls, then returns `data.result`. The mock
resolves synchronously and returns the result shape directly.

## date_time filter types

Requests share a `date_time` object with a `filter_type`:

- `1` Single Hour: `start_date` + `start_time`
- `2` Range of Hours (same day): `start_date` + `start_time` + `end_time`
- `3` Single Day: `start_date`
- `4` Date Range: `start_date` + `end_date`

## Endpoints and how the agent uses them

### POST /v1/env_params

The core point query and the one every ranking rests on. Body: `latitude`,
`longitude`, `temperature` (the coarse reference reading the API downscales from),
`date_time` and an optional `parameters` list. The result carries `metadata`
(timezone, timestamps) and `locations`, where each location holds `lat`, `lon`,
`elevation`, the echoed reference `temperature` and a `parameters` block of
time-aligned hourly arrays: `heat_index_celsius`, `apparent_temperature_celsius`,
`wet_bulb_temperature_celsius`, `relative_humidity_percent`, `cloud_cover_octas`,
`precipitation_mm`, several air-quality and gas fields, plus a `solar_irradiance`
block. The API returns felt-temperature fields directly (heat index, apparent,
wet-bulb); it does not return a raw air-temperature array, so `feels_like` is
driven by `apparent_temperature_celsius` and falls back to `heat_index_celsius`.

Used by `get_point_conditions`, the coolest-hour planner and the route planner.

### POST /v1/streetview

Street-level semantic segmentation at a point: `latitude`, `longitude`,
`vertical_angle`, `horizontal_angle`, `back_view`. The result carries
`front.segments`, percentage land-cover of the view (`building`, `sky`, `tree`,
`grass`, `road`, `fence`, `others`), plus the imagery. The live client derives the
shade signal the route planner needs from those segments:

- `shade_fraction` = building + tree + fence (the parts of the view that cast or
  represent shade), capped at 1.0
- `sky_view_factor` = sky
- `dominant_surface` from the ground labels (paved vs vegetation, else mixed)

Coverage is sparse: a point with no imagery returns an error, so the route planner
skips shade for that sample (treats it as fully exposed) rather than failing.

### POST /v1/heatmap

A thermal field over a GeoJSON `polygon_aoi` at a `granularity` of 60, 80 or 100
metres. `analytic_type` selects the per-cell value: `tcm` (temperature snapshot,
the default), `time_of_measure` (the hour a cell peaks) or `persistence` (hours
past `threshold`, with `direction`). The result is `{map_data, stats_data}`, a
GeoJSON FeatureCollection of cells plus a count. The live client summarises the
cells into hottest, coolest and mean. On the hackathon tier the areas and windows
we tested returned no cells, so the live summary reports `cell_count` 0 with a
note; the route and time analyses do not depend on it.

Used by the `get_area_heat_snapshot` tool.

### POST /v1/heat_intelligence

Point analysis: `latitude`, `longitude`, `temperature`, `date`, `analysis`. The
live result is a `download_link` to a report rather than inline figures, so the
agent's heat-risk band is computed from the env_params felt temperature against
the NWS bands rather than from this endpoint.

### POST /v1/satellite

Satellite land-cover segmentation for a point (`sat.latitude`, `sat.longitude`,
`date_time`, `granularity`). The result carries a `segmentation.segments`
breakdown (for example road vs earth) plus base64 imagery, which the client drops.
Available in the adapter for completeness; not on a tool path.

### GET /v1/status/{activity_id}

Polls an async submission until `data.status` is `Completed`, then returns the
result.

## Derived comfort metrics

The API returns felt-temperature fields directly. Where the mock computes them,
and to explain the numbers, we use published formulas so the values are physical:

- Heat index: NWS Rothfusz regression (Rothfusz 1990, NWS Technical Attachment
  SR 90-23), with the low-RH and high-RH adjustments.
- Wet-bulb temperature: Stull (2011), J. Appl. Meteor. Climatol. 50, 2267-2269.
- Relative humidity from temperature and dewpoint: the Magnus formula.
- Heat-risk bands: the NWS heat-index categories (caution, extreme caution,
  danger, extreme danger), in degrees Celsius of felt temperature.

## Verified against a live key

Confirmed on 2026-08-18 with a real key: the `api-key` header, the async
`data`/`activity_id`/`status`/`result` envelope, the `env_params` result schema
(no raw air-temperature array), the `streetview` segmentation shape, the
`heatmap` `{map_data, stats_data}` shape, the `heat_intelligence` `download_link`
result and the `satellite` segmentation. A live `coolest-time` and `coolest-route`
run against Delhi and Abu Dhabi returned real rankings (captured in `artifacts/`).
