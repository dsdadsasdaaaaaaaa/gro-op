from datetime import datetime, timedelta, timezone

import pytest

from grow_brain.controller import (ControlContext, DeviceInput, SensorSnapshot, decide, learn_gain, light_window)
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
         safety_max=35.0, safety_min=12.0, switched=None, on_readings=None, on_tags=None):
    roles = ["light", "exhaust_fan", "intake_fan", "circulation_fan", "humidifier", "dehumidifier", "heater", "cooler"]
    states = states or {}
    overrides = overrides or {}
    switched, on_readings, on_tags = switched or {}, on_readings or {}, on_tags or {}
    devices = {r: DeviceInput(r, f"switch.{r}", states.get(r, "off"), True, switched.get(r), overrides.get(r), None,
                              on_readings.get(r), on_tags.get(r)) for r in roles}
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


NOW = datetime(2026, 9, 20, 12, 7, tzinfo=timezone.utc)


def test_cooling_runs_in_pulses_sized_to_the_excess():
    # veg max is 28. 28.6 → excess 1.1 °C → at 0.25 °C/min that is a 264 s pulse
    d = decide(_ctx(28.6, 60.0))
    assert d["exhaust_fan"].desired is True and "264 s pulse" in d["exhaust_fan"].reason and d["exhaust_fan"].tag == "exhaust_cool"
    # 2 minutes into that pulse the (stale) reading is still 28.6: keep going
    d = decide(_ctx(28.6, 60.0, states={"exhaust_fan": "on"}, switched={"exhaust_fan": NOW - timedelta(seconds=120)},
                    on_readings={"exhaust_fan": 28.6}, on_tags={"exhaust_fan": "exhaust_cool"}))
    assert d["exhaust_fan"].desired is True
    # pulse over: stop and wait for the sensor even though the reading is still above max
    d = decide(_ctx(28.6, 60.0, states={"exhaust_fan": "on"}, switched={"exhaust_fan": NOW - timedelta(seconds=270)},
                    on_readings={"exhaust_fan": 28.6}, on_tags={"exhaust_fan": "exhaust_cool"}))
    assert d["exhaust_fan"].desired is False and d["exhaust_fan"].tag == "exhaust_cool_done"
    # resting: no new pulse for LAG_S after it stopped
    d = decide(_ctx(28.6, 60.0, switched={"exhaust_fan": NOW - timedelta(seconds=200)}))
    assert d["exhaust_fan"].desired is False and "resting" in d["exhaust_fan"].reason
    # far above max: continuous, no pulsing
    assert decide(_ctx(29.6, 60.0, switched={"exhaust_fan": NOW - timedelta(seconds=200)}))["exhaust_fan"].desired is True


def test_learned_gain_changes_the_pulse_length():
    ctx = _ctx(28.6, 60.0)
    ctx.cool_gain = 0.5
    assert "132 s pulse" in decide(ctx)["exhaust_fan"].reason


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
    # real-world false positives seen on Levi's HA
    assert suggest_role("input_boolean.man_cave_overheat_active", "Overheat Active", None, None) is None
    assert suggest_role("switch.exhaust_led", "exhaust LED", None, None) is None
    assert suggest_role("switch.humidifier_auto_off_enabled", "humidifier Auto-off enabled", None, None) is None
    assert suggest_role("sensor.backup_last_attempted", "Backup Last attempted automatic backup", "timestamp", None) is None
    assert suggest_role("sensor.man_cave_circadian_color_temp", "Man Cave Circadian Color Temp", None, "K") is None
    assert suggest_role("sensor.humidifier_auto_off_at", "humidifier Auto-off at", "timestamp", None) is None
    assert suggest_role("sensor.h5074_8081_temperature", "grow hygrometer Temperature", "temperature", "°C") == "temperature_sensor"
    assert suggest_role("switch.dehumidifer", "dehumidifer", None, None) == "dehumidifier"
    assert suggest_role("switch.room", "Grow light", None, None) == "light"
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


def test_plan_phases_and_anchoring():
    from datetime import date
    from grow_brain.plan import build_plan, PHASES, current_phase_key
    prof = {"stage": "seedling", "start_date": "2026-09-19", "stage_started": "2026-09-19", "expected_flower_days": 65}
    plan = build_plan(prof, date(2026, 9, 20), 1, 1, planted=False)
    assert plan["current_phase"] == "germination"
    assert [p["status"] for p in plan["phases"]][:3] == ["current", "upcoming", "upcoming"]
    assert plan["phases"][0]["start_date"] == "2026-09-19"
    plan = build_plan(prof, date(2026, 9, 22), 3, 3, planted=True)
    assert plan["current_phase"] == "seedling"
    # flower anchoring: harvest = flower start + 65 days, flush is the last 7
    prof2 = {"stage": "flower", "start_date": "2026-09-19", "stage_started": "2026-11-10", "flower_start_date": "2026-11-10", "expected_flower_days": 65}
    plan = build_plan(prof2, date(2026, 11, 20), 10, 62, planted=True)
    byk = {p["key"]: p for p in plan["phases"]}
    assert plan["current_phase"] == "flower_stretch" and byk["veg"]["status"] == "done"
    assert byk["flower_stretch"]["start_date"] == "2026-11-10"
    assert byk["dry"]["start_date"] == "2027-01-14"  # 2026-11-10 + 65 days
    assert byk["flush"]["start_date"] == "2027-01-07"
    assert current_phase_key("flower", 55, True) == "flower_ripen"
    assert current_phase_key("done", 0, True) is None
    assert len(PHASES) == 9


def test_standby_turns_everything_off_but_respects_overrides():
    ctx = _ctx(30.0, 40.0)  # hot and dry: would normally run exhaust + cooler + humidifier
    ctx.standby = True
    d = decide(ctx)
    assert all(dec.desired is False for dec in d.values())
    assert d["light"].reason == "tent in standby"
    ctx = _ctx(30.0, 40.0, overrides={"light": "on"})
    ctx.standby = True
    assert decide(ctx)["light"].desired is True  # a manual "on" still wins


def test_humidifier_pulses_toward_the_band():
    # veg band 55-65, target = 57. From 48: deficit 9 → 360 s at 1.5 pts/min → capped at 300 s
    d = decide(_ctx(25.0, 48.0))
    assert d["humidifier"].desired is True and "300 s pulse" in d["humidifier"].reason and d["humidifier"].tag == "humidifier"
    # from 55.5: deficit 1.5 → 60 s minimum pulse
    assert "60 s pulse" in decide(_ctx(25.0, 55.5))["humidifier"].reason
    # inside the band: nothing
    assert decide(_ctx(25.0, 58.0))["humidifier"].desired is False
    # mid-pulse with a stale reading: keep going until the planned time
    d = decide(_ctx(25.0, 48.0, states={"humidifier": "on"}, switched={"humidifier": NOW - timedelta(seconds=100)},
                    on_readings={"humidifier": 48.0}, on_tags={"humidifier": "humidifier"}))
    assert d["humidifier"].desired is True
    d = decide(_ctx(25.0, 48.0, states={"humidifier": "on"}, switched={"humidifier": NOW - timedelta(seconds=310)},
                    on_readings={"humidifier": 48.0}, on_tags={"humidifier": "humidifier"}))
    assert d["humidifier"].desired is False and d["humidifier"].tag == "humidifier_done"
    # the sensor caught up mid-pulse and shows the target: stop early
    d = decide(_ctx(25.0, 57.5, states={"humidifier": "on"}, switched={"humidifier": NOW - timedelta(seconds=100)},
                    on_readings={"humidifier": 48.0}, on_tags={"humidifier": "humidifier"}))
    assert d["humidifier"].desired is False and d["humidifier"].tag == "humidifier_done"
    # resting after a pulse even though the reading is still low; ready again after LAG_S
    d = decide(_ctx(25.0, 50.0, switched={"humidifier": NOW - timedelta(seconds=120)}))
    assert d["humidifier"].desired is False and "resting" in d["humidifier"].reason
    assert decide(_ctx(25.0, 50.0, switched={"humidifier": NOW - timedelta(seconds=320)}))["humidifier"].desired is True


def test_no_preloading_before_an_air_exchange():
    # seedling band 65-75: three minutes before an exchange, 69 % is in band and stays that way (no wasted mist)
    ctx = _ctx(25.0, 69.0, stage="seedling")
    ctx.now_local = ctx.now_local.replace(minute=27)
    assert decide(ctx)["humidifier"].desired is False


def test_learn_gain_blends_and_rejects_nonsense():
    assert learn_gain(None, 2.0, 0.2, 6.0) == 2.0
    assert learn_gain(2.0, 1.0, 0.2, 6.0) == 1.7
    assert learn_gain(2.0, 9.0, 0.2, 6.0) == 2.0      # out of range: ignored
    assert learn_gain(None, -0.5, 0.2, 6.0) is None


def test_exhaust_waits_for_a_real_humidity_excess():
    # veg max 65: 67 is not worth dumping the tent's humidity for; 69 is
    assert decide(_ctx(25.0, 67.0))["exhaust_fan"].desired is False
    assert decide(_ctx(25.0, 69.0))["exhaust_fan"].desired is True
    # once on, it stops as soon as RH is back under the max instead of 4 points lower
    assert decide(_ctx(25.0, 64.5, states={"exhaust_fan": "on"}))["exhaust_fan"].desired is False


def test_seedlings_get_shorter_air_exchange():
    ctx = _ctx(25.0, 70.0, stage="seedling")
    ctx.now_local = ctx.now_local.replace(minute=2)   # minute 2 of the 30-minute period → 3-minute pulse is on
    assert decide(ctx)["exhaust_fan"].desired is True and "3 min every 30" in decide(ctx)["exhaust_fan"].reason
    ctx.now_local = ctx.now_local.replace(minute=4)   # would still be on under the old 5-of-20 rule
    assert decide(ctx)["exhaust_fan"].desired is False


def test_humidifier_waits_while_the_exhaust_runs():
    # veg: 28.6 °C starts a cooling pulse; 48 % RH would start a humidifier pulse, but not into an exhausting tent
    d = decide(_ctx(28.6, 48.0))
    assert d["exhaust_fan"].desired is True
    assert d["humidifier"].desired is False and "waiting for the exhaust" in d["humidifier"].reason
    # a pulse that is already running keeps going (it partly offsets the dry air; the measurement is discarded)
    d = decide(_ctx(28.6, 48.0, states={"humidifier": "on"}, switched={"humidifier": NOW - timedelta(seconds=60)},
                    on_readings={"humidifier": 48.0}, on_tags={"humidifier": "humidifier"}))
    assert d["humidifier"].desired is True


def test_air_exchange_skipped_when_the_exhaust_just_ran():
    at = NOW.replace(minute=1)   # inside the 3-minute window
    ctx = _ctx(25.0, 70.0, stage="seedling", switched={"exhaust_fan": at - timedelta(minutes=4)})
    ctx.now_local = at
    assert decide(ctx)["exhaust_fan"].desired is False
    ctx = _ctx(25.0, 70.0, stage="seedling", switched={"exhaust_fan": at - timedelta(minutes=15)})
    ctx.now_local = at
    assert decide(ctx)["exhaust_fan"].desired is True
    # a running exchange is not cut short by its own start time
    ctx = _ctx(25.0, 70.0, stage="seedling", states={"exhaust_fan": "on"}, switched={"exhaust_fan": at - timedelta(seconds=60)},
               on_tags={"exhaust_fan": "exhaust_duty"})
    ctx.now_local = at
    assert decide(ctx)["exhaust_fan"].desired is True
