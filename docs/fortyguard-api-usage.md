# FortyGuard Temperature API usage

How Cool Route Planner uses the FortyGuard Temperature API. The endpoint surface,
request shapes and the `api-key` header were taken from the public API docs at
docs-api.fortyguard.com and confirmed against the live error responses. The
project talks to the API only through one adapter (`src/coolroute/fortyguard/`),
so the mock and the live backend are interchangeable.

## Basics

- Base URL: `https://api.fortyguard.com/v1`
- Auth: the key goes in the `api-key` request header. A call without it returns
  `401 {"error": true, "status_code": 401, "details": {"message": "..."}}`.
- All data endpoints are `POST` with a JSON body. Status is a `GET`.
- Temperature is 2m above ground. Values are degrees Celsius.
- Data window: `start_date` must fall between 2019-01-01 and 12 hours past the
  current time. The API forecasts at most about 12 hours ahead. Our adapter
  enforces this before the call (`validate_window`), matching the API, which
  rejects out-of-window requests (and per the FAQ a rejected call costs no
  credits).
- Submissions are asynchronous: an endpoint returns an `activity_id` and the
  final payload is polled from `GET /v1/status/{activity_id}`. The live client
  submits then polls; if a response already carries the result it is used
  directly. The mock resolves synchronously.

## date_time filter types

Requests share a `date_time` object with a `filter_type`:

- `1` Single Hour: `start_date` + `start_time`
- `2` Range of Hours (same day): `start_date` + `start_time` + `end_time`
- `3` Single Day: `start_date`
- `4` Date Range: `start_date` + `end_date`

## Endpoints and how the agent uses them

### POST /v1/env_params

The core point query. Body: `latitude`, `longitude`, `temperature` (the coarse
reference reading the API downscales from), `date_time` and an optional
`parameters` list to select outputs. The response carries time-aligned arrays per
location: `air_temperature_celsius`, `heat_index_celsius`,
`apparent_temperature_celsius`, `wet_bulb_temperature_celsius`,
`relative_humidity_percent`, `cloud_cover_octas`, plus air-quality and gas fields
and a `solar_irradiance` block, alongside `metadata` (timezone and timestamps)
and `locations` (lat, lon, elevation).

Used by the `get_point_conditions` tool and by the coolest-hour and coolest-route
planners. Felt temperature drives every ranking.

### POST /v1/heatmap

A high-resolution thermal field over a GeoJSON `polygon_aoi` at a `granularity`
of 60, 80 or 100 metres. `analytic_type` selects what each tile carries: `tcm` (a
temperature snapshot, the default), `time_of_measure` (the hour a tile peaks) or
`persistence` (the longest run of hours past `threshold`, with `direction` above
or below). Supports forecasting up to 12 hours.

Used by the `get_area_heat_snapshot` tool to report the hottest cell, the coolest
cell and the mean over an area.

### POST /v1/streetview

Street-level view context at a point: `latitude`, `longitude`, `vertical_angle`,
`horizontal_angle`, `back_view`. We read it for shade context (shade fraction,
sky-view factor, dominant surface).

Used by the `get_street_shade` tool and by the route planner, where shade is part
of the exposure score.

### POST /v1/heat_intelligence

Environmental analysis at a point: `latitude`, `longitude`, `temperature`,
`date`, `analysis` (for example `["environmental"]`). Returns a heat-risk view we
map to a band.

### POST /v1/satellite

Satellite-derived thermal data for a point (`sat.latitude`, `sat.longitude`,
`date_time`, `granularity`). Available in the adapter for completeness.

### GET /v1/status/{activity_id}

Polls an async submission until it reports completed, then returns the result.

## Derived comfort metrics

The API returns felt-temperature fields directly. Where the mock computes them,
and to explain the numbers, we use published formulas so the values are physical:

- Heat index: NWS Rothfusz regression (Rothfusz 1990, NWS Technical Attachment
  SR 90-23), with the low-RH and high-RH adjustments.
- Wet-bulb temperature: Stull (2011), J. Appl. Meteor. Climatol. 50, 2267-2269.
- Relative humidity from temperature and dewpoint: the Magnus formula, so RH
  falls as the temperature climbs, the way it does in reality.
- Heat-risk bands: the NWS heat-index categories (caution, extreme caution,
  danger, extreme danger), expressed in degrees Celsius of felt temperature.

## Confirmed vs pending the key

Confirmed anonymously from the public docs and live error bodies: the endpoint
paths, the `api-key` header, the request bodies, the `env_params` response
schema, the `date_time` and `analytic_type` semantics and the 2019 / 12-hour
window. Pending a real key at integration time: the exact `status` field values
in the async flow and the precise `heatmap` response envelope. The live client is
written to the documented contract and these two points are flagged in
`src/coolroute/fortyguard/live.py`.
