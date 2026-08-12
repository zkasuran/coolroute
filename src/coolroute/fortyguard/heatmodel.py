"""Deterministic synthetic heat model for the offline mock backend.

Everything here is generated, never a recorded real reading, and every mock API
response is tagged `"source": "mock"`. The model is deterministic in its inputs
so tests are stable and a demo is reproducible.

The derived comfort metrics use published formulas so the numbers are physically
plausible rather than arbitrary:
  - Heat index: NWS Rothfusz regression (Rothfusz 1990, NWS Technical Attachment
    SR 90-23), with the low-RH and high-RH adjustments.
  - Wet-bulb temperature: Stull (2011), "Wet-Bulb Temperature from Relative
    Humidity and Air Temperature", J. Appl. Meteor. Climatol. 50, 2267-2269.
"""
from __future__ import annotations

import hashlib
import math

# Rough seasonal diurnal envelopes for a few hot cities, mid-summer.
# (pre-dawn low degC, afternoon high degC, typical dewpoint degC). Humidity is
# derived from temperature and dewpoint per hour, so relative humidity falls as
# the temperature climbs, the way it does in reality. Holding RH constant makes
# the heat index explode at the afternoon peak.
CITY_CLIMATE = {
    "abu_dhabi": (33.0, 44.0, 21.0),
    "delhi": (29.0, 39.0, 24.0),
    "dubai": (33.0, 43.0, 21.0),
    "phoenix": (28.0, 43.0, 7.0),
    "default": (26.0, 38.0, 16.0),
}

PEAK_HOUR = 15.0  # local hour of the daily temperature maximum


def rh_from_dewpoint(temp_c: float, dewpoint_c: float) -> float:
    """Relative humidity (%) from air temperature and dewpoint (Magnus formula)."""
    a, b = 17.625, 243.04
    gamma_t = (a * temp_c) / (b + temp_c)
    gamma_d = (a * dewpoint_c) / (b + dewpoint_c)
    rh = 100.0 * math.exp(gamma_d - gamma_t)
    return round(max(1.0, min(100.0, rh)), 1)


def _hash_unit(*parts: object) -> float:
    """Deterministic pseudo-random value in [0, 1) from the given parts."""
    key = "|".join(str(p) for p in parts).encode()
    digest = hashlib.sha256(key).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def diurnal_temp(lo: float, hi: float, hour: float) -> float:
    """Air temperature at a given local hour on a smooth daily curve."""
    mean = (lo + hi) / 2.0
    amp = (hi - lo) / 2.0
    return mean + amp * math.cos(2.0 * math.pi * (hour - PEAK_HOUR) / 24.0)


def uhi_offset(latitude: float, longitude: float) -> float:
    """Urban-heat-island offset for a location, deg C.

    Dense paved cells run hotter, parks and water run cooler. Deterministic on
    the rounded coordinate so nearby points share a micro-climate.
    """
    u = _hash_unit(round(latitude, 3), round(longitude, 3))
    return round((u * 6.0) - 2.5, 2)  # roughly [-2.5, +3.5]


def shade_fraction(latitude: float, longitude: float) -> float:
    """Fraction of the point shaded by canopy or built form, in [0, 1]."""
    return round(_hash_unit("shade", round(latitude, 4), round(longitude, 4)), 3)


def air_temperature(lo: float, hi: float, hour: float, latitude: float, longitude: float) -> float:
    """2m-above-ground air temperature for a point and local hour."""
    return round(diurnal_temp(lo, hi, hour) + uhi_offset(latitude, longitude), 2)


def heat_index_c(temp_c: float, rh: float) -> float:
    """NWS Rothfusz heat index. Input/formula in Fahrenheit, returned in C."""
    t = temp_c * 9.0 / 5.0 + 32.0
    if t < 80.0:
        # Simple form below 80F; the regression is only valid at higher temps.
        hi = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    else:
        hi = (
            -42.379 + 2.04901523 * t + 10.14333127 * rh
            - 0.22475541 * t * rh - 6.83783e-3 * t * t
            - 5.481717e-2 * rh * rh + 1.22874e-3 * t * t * rh
            + 8.5282e-4 * t * rh * rh - 1.99e-6 * t * t * rh * rh
        )
        if rh < 13.0 and 80.0 <= t <= 112.0:
            hi -= ((13.0 - rh) / 4.0) * math.sqrt((17.0 - abs(t - 95.0)) / 17.0)
        elif rh > 85.0 and 80.0 <= t <= 87.0:
            hi += ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return round((hi - 32.0) * 5.0 / 9.0, 2)


def wet_bulb_c(temp_c: float, rh: float) -> float:
    """Wet-bulb temperature, Stull (2011) approximation, deg C."""
    t = temp_c
    tw = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return round(tw, 2)


def apparent_temperature_c(temp_c: float, rh: float, shade: float, hour: float) -> float:
    """Felt temperature: heat index, eased down where a point is shaded at high sun."""
    hi = heat_index_c(temp_c, rh)
    # Solar load peaks near midday; shade removes up to ~4C of it.
    solar = max(0.0, math.cos(2.0 * math.pi * (hour - 13.0) / 24.0))
    relief = shade * solar * 4.0
    return round(hi - relief, 2)


def heat_risk_band(feels_like_c: float) -> str:
    """NWS heat-index risk bands, expressed in deg C of 'feels like'."""
    if feels_like_c >= 54.0:
        return "extreme_danger"
    if feels_like_c >= 41.0:
        return "danger"
    if feels_like_c >= 32.0:
        return "extreme_caution"
    if feels_like_c >= 27.0:
        return "caution"
    return "safe"
