from datetime import datetime, timedelta, timezone

import pytest

from grow_brain.controller import (ControlContext, DeviceInput, SensorSnapshot, decide, light_window)
from grow_brain.devices import automap, suggest_role
from grow_brain.targets import Targets, apply_overrides, stage_defaults, vpd_kpa


def test_vpd_reasonable():
    # 25°C / 60% RH is a classic ~1.0 kPa veg VPD (leaf 1°C cooler)
    assert 0.9 <= vpd_kpa(25, 60) <= 1.1
    assert vpd_kpa(20, 90) < 0.3
    assert vpd_kpa(30, 30) > 2.0


def test_stage_defaults_progress():
    assert stage_defaults("veg").light_hours == 18
    assert stage_defaults("flower", 5).light_hours == 12
    assert stage_defaults("flower", 60).humidity_max < stage_defaults("flower", 5).humidity_max
    assert stage_defaults("drying").light_hours == 0


def test_overrides_are_bounded():
    t = apply_overrides(stage_defaults("veg"), {"temp_max_c": 99, "humidity_min": -5}, "advisor")
    assert t.temp_max_c == 32.0
    assert t.humidity_min == 25.0
    assert t.source == "advisor"


def test_light_window():
    tz = timezone.utc
    on, nxt = light_window(datetime(2026, 9, 20, 12, 0, tzinfo=tz), "06:00", 18)
    assert on and nxt == datetime(2026, 9, 21, 0, 0, tzinfo=tz)
    on, nxt = light_window(datetime(2026, 9, 20, 2, 0, tzinfo=tz), "06:00", 18)
    assert not on and nxt == datetime(2026, 9, 20, 6, 0, tzinfo=tz)
    on, _ = light_window(datetime(2026, 9, 20, 20, 0, tzinfo=tz), "18:00", 12)
    assert on


def _ctx(temp, rh, stage="veg", lights_on=True, states=None, paused=False, overrides=None, stale=False,
         safety_max=35.0, safety_min=12.0):
    roles = ["light", "exhaust_fan", "intake_fan", "circulation_fan", "humidifier", "dehumidifier", "heater", "cooler"]
    states = states or {}
    overrides = overrides or {}
    devices = {r: DeviceInput(r, f"switch.{r}", states.get(r, "off"), True, None, overrides.get(r), None) for r in roles}
    day = stage_defaults(stage)
    t = day if lights_on else day.for_night()
    return ControlContext(
        now_local=datetime(2026, 9, 20, 12, 7, tzinfo=timezone.utc), stage=stage, targets=t, day_targets=day,
        light_scheduled_on=lights_on, lights_on=lights_on,
        sensor=SensorSnapshot(temp, rh, vpd_kpa(temp, rh) if temp is not None else None, None, datetime.now(timezone.utc), stale),
        safety_temp_max_c=safety_max, safety_temp_min_c=safety_min, exhaust_ducted=False, paused=paused, devices=devices,
    )


def test_in_range_is_quiet():
    d = decide(_ctx(25.0, 60.0))
    assert d["light"].desired is True
    assert d["circulation_fan"].desired is True
    assert d["exhaust_fan"].desired is False  # minute 7 of 20 → duty window (0-5) closed
    assert d["humidifier"].desired is False and d["dehumidifier"].desired is False
    assert d["heater"].desired is False and d["cooler"].desired is False


def test_hot_turns_on_exhaust_and_cooler():
    d = decide(_ctx(29.5, 60.0))
    assert d["exhaust_fan"].desired is True and d["cooler"].desired is True and d["heater"].desired is False
    assert d["intake_fan"].desired is True


def test_hysteresis_keeps_exhaust_on():
    # veg max is 28; at 27.5 with exhaust already on it should stay on (hyst 1.0)
    d = decide(_ctx(27.5, 60.0, states={"exhaust_fan": "on"}))
    assert d["exhaust_fan"].desired is True
    d = decide(_ctx(26.5, 60.0, states={"exhaust_fan": "on"}))
    assert d["exhaust_fan"].desired is False


def test_dry_turns_on_humidifier():
    d = decide(_ctx(25.0, 48.0))
    assert d["humidifier"].desired is True and d["dehumidifier"].desired is False


def test_humid_turns_on_dehumidifier_and_exhaust():
    d = decide(_ctx(25.0, 72.0))
    assert d["dehumidifier"].desired is True and d["exhaust_fan"].desired is True


def test_night_band_is_cooler():
    # 21°C at night in veg is fine (band ~20-26), by day it would trigger the heater (min 23)
    assert decide(_ctx(21.0, 60.0, lights_on=False))["heater"].desired is False
    assert decide(_ctx(21.0, 60.0, lights_on=True))["heater"].desired is True


def test_safety_overheat_overrides_manual_and_pause():
    d = decide(_ctx(36.0, 50.0, paused=True, overrides={"light": "on", "exhaust_fan": "off"}))
    assert d["light"].desired is False and d["light"].force
    assert d["exhaust_fan"].desired is True and d["exhaust_fan"].force


def test_manual_override_and_pause():
    d = decide(_ctx(29.5, 60.0, overrides={"exhaust_fan": "off"}))
    assert d["exhaust_fan"].desired is False and "manual" in d["exhaust_fan"].reason
    d = decide(_ctx(29.5, 60.0, paused=True))
    assert d["exhaust_fan"].desired is None


def test_stale_sensor_safe_mode():
    d = decide(_ctx(None, None, stale=True))
    assert d["exhaust_fan"].desired is True
    assert d["humidifier"].desired is False and d["heater"].desired is False
    assert d["light"].desired is True  # schedule still runs


def test_critical_humidity_forces():
    d = decide(_ctx(24.0, 88.0, overrides={"dehumidifier": "off"}))
    assert d["dehumidifier"].desired is True and d["dehumidifier"].force


def test_drying_stage_lights_off():
    d = decide(_ctx(18.0, 58.0, stage="drying"))
    assert d["light"].desired is False


def test_suggest_role_and_automap():
    assert suggest_role("switch.grow_exhaust_fan", "Grow Exhaust Fan", None, None) == "exhaust_fan"
    assert suggest_role("switch.grow_light", "Grow Light", None, None) == "light"
    assert suggest_role("switch.tent_humidifier", "Tent Humidifier", None, None) == "humidifier"
    assert suggest_role("switch.tent_dehumidifier", "Tent Dehumidifier", None, None) == "dehumidifier"
    assert suggest_role("sensor.tent_temperature", "Tent Temperature", "temperature", "°C") == "temperature_sensor"
    assert suggest_role("sensor.tent_humidity", "Tent Humidity", "humidity", "%") == "humidity_sensor"
    assert suggest_role("sensor.grow_light_power", "Grow Light Power", "power", "W") is None
    ents = [
        {"entity_id": "switch.grow_light", "name": "Grow Light", "suggested_role": "light"},
        {"entity_id": "switch.grow_exhaust_fan", "name": "Grow Exhaust Fan", "suggested_role": "exhaust_fan"},
        {"entity_id": "switch.grow_clip_fan", "name": "Grow Clip Fan", "suggested_role": "circulation_fan"},
        {"entity_id": "sensor.tent_temperature", "name": "Tent Temperature", "suggested_role": "temperature_sensor"},
        {"entity_id": "sensor.tent_humidity", "name": "Tent Humidity", "suggested_role": "humidity_sensor"},
    ]
    m = automap(ents)
    assert m["light"] == "switch.grow_light" and m["exhaust_fan"] == "switch.grow_exhaust_fan"
    assert m["circulation_fan"] == "switch.grow_clip_fan"
    assert m["temperature_sensor"] == "sensor.tent_temperature"
