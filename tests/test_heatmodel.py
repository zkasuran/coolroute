import math

from coolroute.fortyguard import heatmodel as hm


def test_diurnal_orders_dawn_cooler_than_midafternoon():
    lo, hi = 29.0, 39.0
    assert hm.diurnal_temp(lo, hi, 6) < hm.diurnal_temp(lo, hi, 15)
    # peak sits near 15:00
    temps = {h: hm.diurnal_temp(lo, hi, h) for h in range(24)}
    assert max(temps, key=temps.get) == 15


def test_uhi_offset_is_deterministic_and_bounded():
    a = hm.uhi_offset(28.61, 77.21)
    b = hm.uhi_offset(28.61, 77.21)
    assert a == b
    assert -2.6 <= a <= 3.6


def test_heat_index_amplifies_humid_heat():
    # At 40C the heat index in humid air should read hotter than dry air.
    assert hm.heat_index_c(40.0, 70.0) > hm.heat_index_c(40.0, 20.0)
    # And hotter than the raw temperature.
    assert hm.heat_index_c(40.0, 70.0) > 40.0


def test_wet_bulb_below_dry_bulb_and_finite():
    tw = hm.wet_bulb_c(38.0, 60.0)
    assert tw < 38.0 and math.isfinite(tw)


def test_shade_relief_only_reduces_and_only_by_day():
    hot = hm.apparent_temperature_c(42.0, 50.0, shade=0.0, hour=13)
    shaded = hm.apparent_temperature_c(42.0, 50.0, shade=1.0, hour=13)
    assert shaded < hot  # shade at high sun cools the felt temperature
    night = hm.apparent_temperature_c(30.0, 50.0, shade=1.0, hour=2)
    assert night == hm.apparent_temperature_c(30.0, 50.0, shade=0.0, hour=2)


def test_risk_bands():
    assert hm.heat_risk_band(20) == "safe"
    assert hm.heat_risk_band(28) == "caution"
    assert hm.heat_risk_band(35) == "extreme_caution"
    assert hm.heat_risk_band(45) == "danger"
    assert hm.heat_risk_band(60) == "extreme_danger"
