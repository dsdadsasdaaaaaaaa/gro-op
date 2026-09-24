from datetime import datetime, timedelta, timezone

import pytest

from grow_brain.controller import (ControlContext, DeviceInput, SensorSnapshot, decide, exchange_plan, humidity_aim, learn_gain,
                                   light_window)
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
    assert d["exhaust_fan"].desired is False and "by hand" in d["exhaust_fan"].reason
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
    assert suggest_role("input_boolean.basement_overheat_active", "Overheat Active", None, None) is None
    assert suggest_role("switch.exhaust_led", "exhaust LED", None, None) is None
    assert suggest_role("switch.humidifier_auto_off_enabled", "humidifier Auto-off enabled", None, None) is None
    assert suggest_role("sensor.backup_last_attempted", "Backup Last attempted automatic backup", "timestamp", None) is None
    assert suggest_role("sensor.basement_circadian_color_temp", "Basement Circadian Color Temp", None, "K") is None
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
    # veg band 55-65: aim a third of the way in, 58.3. From 48: deficit 10.3 → capped at 300 s
    d = decide(_ctx(25.0, 48.0))
    assert d["humidifier"].desired is True and "300 s pulse" in d["humidifier"].reason and d["humidifier"].tag == "humidifier"
    # from 57.0: deficit 1.3 → 60 s minimum pulse
    assert "60 s pulse" in decide(_ctx(25.0, 57.0))["humidifier"].reason
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
    d = decide(_ctx(25.0, 58.5, states={"humidifier": "on"}, switched={"humidifier": NOW - timedelta(seconds=100)},
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


def test_fresh_air_swaps_are_sized_to_the_tent():
    # seedlings need about 3 min of fresh air an hour; at 2 % RH lost per minute of swap, 90 s swaps (≈3 points
    # each) every 30 min. Later stages keep 5 min every 20. A tent that barely loses humidity gets rarer, longer swaps.
    assert exchange_plan("seedling", 2.0) == (90.0, 1800.0)
    assert exchange_plan("veg", 2.0) == (300.0, 1200.0)
    assert exchange_plan("seedling", 1.0) == (180.0, 3600.0)
    assert exchange_plan("seedling", 6.0) == (90.0, 1800.0)       # never shorter than 90 s
    # with no record of the last run, swaps follow the clock: on at 12:00:30, off by 12:02
    ctx = _ctx(25.0, 70.0, stage="seedling")
    ctx.now_local = ctx.now_local.replace(minute=0, second=30)
    d = decide(ctx)["exhaust_fan"]
    assert d.desired is True and "90 s every 30 min" in d.reason and d.tag == "exhaust_duty" and d.basis == 70.0
    ctx.now_local = ctx.now_local.replace(minute=2)
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


def test_fresh_air_is_counted_from_the_last_exhaust_run():
    # the exhaust stopped 15 min ago (for any reason: a cooling pulse swaps air too) → next swap only after 28.5 min
    assert decide(_ctx(25.0, 70.0, stage="seedling", switched={"exhaust_fan": NOW - timedelta(minutes=15)}))["exhaust_fan"].desired is False
    assert decide(_ctx(25.0, 70.0, stage="seedling", switched={"exhaust_fan": NOW - timedelta(minutes=29)}))["exhaust_fan"].desired is True
    # a running swap keeps going for its 90 s, then stops
    run = dict(stage="seedling", states={"exhaust_fan": "on"}, on_tags={"exhaust_fan": "exhaust_duty"}, on_readings={"exhaust_fan": 70.0})
    assert decide(_ctx(25.0, 70.0, switched={"exhaust_fan": NOW - timedelta(seconds=60)}, **run))["exhaust_fan"].desired is True
    assert decide(_ctx(25.0, 70.0, switched={"exhaust_fan": NOW - timedelta(seconds=95)}, **run))["exhaust_fan"].desired is False


def test_a_swap_waits_for_fresh_mist_to_settle():
    due = {"exhaust_fan": NOW - timedelta(minutes=29)}
    ctx = _ctx(25.0, 70.0, stage="seedling", switched={**due, "humidifier": NOW - timedelta(seconds=60)})
    assert decide(ctx)["exhaust_fan"].desired is False          # the humidifier stopped a minute ago
    ctx = _ctx(25.0, 70.0, stage="seedling", states={"humidifier": "on"}, switched={**due, "humidifier": NOW - timedelta(seconds=30)},
               on_tags={"humidifier": "humidifier"}, on_readings={"humidifier": 69.0})
    assert decide(ctx)["exhaust_fan"].desired is False          # still misting
    ctx = _ctx(25.0, 70.0, stage="seedling", switched={"exhaust_fan": NOW - timedelta(minutes=40), "humidifier": NOW - timedelta(seconds=60)})
    assert decide(ctx)["exhaust_fan"].desired is True           # but not forever: 10 min overdue goes anyway


def test_humidifier_refills_right_after_a_swap():
    # seedling band 60-75, aim 64. The swap started at 64 % and ran 95 s: at 2 %/min the air is now about 60.8 %,
    # even though the lagging sensor still says 63.5 %. Refill straight away, sized from the prediction.
    ending = dict(stage="seedling", states={"exhaust_fan": "on"}, switched={"exhaust_fan": NOW - timedelta(seconds=95)},
                  on_tags={"exhaust_fan": "exhaust_duty"}, on_readings={"exhaust_fan": 64.0})
    d = decide(_ctx(25.0, 63.5, **ending))
    assert d["exhaust_fan"].desired is False
    h = d["humidifier"]
    assert h.desired is True and h.tag == "humidifier_ff" and abs(h.basis - 60.83) < 0.05 and "127 s pulse" in h.reason
    # the refill runs its planned length even when the (lagging) sensor already reads the aim...
    running = dict(stage="seedling", states={"humidifier": "on"}, switched={"humidifier": NOW - timedelta(seconds=100),
                   "exhaust_fan": NOW - timedelta(seconds=100)}, on_tags={"humidifier": "humidifier_ff"}, on_readings={"humidifier": 60.83})
    assert decide(_ctx(25.0, 64.5, **running))["humidifier"].desired is True
    # ...and then ends with its own tag, so the runtime can learn from how it turned out
    running["switched"]["humidifier"] = NOW - timedelta(seconds=130)
    h = decide(_ctx(25.0, 62.0, **running))["humidifier"]
    assert h.desired is False and h.tag == "humidifier_ff_done"
    # no refill when the tent was high enough that the swap left it inside the aim
    ending["on_readings"] = {"exhaust_fan": 70.0}
    assert decide(_ctx(25.0, 69.0, **ending))["humidifier"].desired is False
    # no refill while a hand override keeps the exhaust running
    ending["on_readings"], ending["overrides"] = {"exhaust_fan": 64.0}, {"exhaust_fan": "on"}
    assert decide(_ctx(25.0, 63.5, **ending))["humidifier"].desired is False


def test_humidity_aim_sits_inside_the_band():
    from grow_brain.targets import stage_defaults as sd
    assert humidity_aim(sd("seedling"), 3.0) == 64.0      # 60-75: min + swap dip + 1
    assert humidity_aim(sd("seedling"), 9.0) == 65.0      # never more than a third of the way in
    assert humidity_aim(sd("veg"), 0.5) == 57.0           # at least 2 points in
    assert humidity_aim(sd("flower"), 9.0, "flower") == 47.0   # flower: a floor just inside the minimum (mould)
    # seedling tent at 63.5 %: under the aim's start point (63) not yet...
    assert decide(_ctx(25.0, 63.5, stage="seedling", switched={"exhaust_fan": NOW - timedelta(minutes=5)}))["humidifier"].desired is False
    # ...at 62.8 % a pulse starts (the old rule waited for 61 %)
    d = decide(_ctx(25.0, 62.8, stage="seedling", switched={"exhaust_fan": NOW - timedelta(minutes=5)}))["humidifier"]
    assert d.desired is True and "under the 64% aim" in d.reason
    # at night there are no swaps to leave room for: back to just inside the minimum
    d = decide(_ctx(25.0, 62.8, stage="seedling", lights_on=False, switched={"exhaust_fan": NOW - timedelta(minutes=5)}))["humidifier"]
    assert d.desired is False and "within" in d.reason


def test_latched_overheat_keeps_the_light_off_even_below_the_limit_and_with_a_dead_sensor():
    ctx = _ctx(30.0, 60.0)
    ctx.safety_latch = "hot"
    d = decide(ctx)
    assert d["light"].desired is False and d["light"].force and d["exhaust_fan"].desired is True
    ctx = _ctx(None, None, stale=True)
    ctx.safety_latch = "hot"
    d = decide(ctx)
    assert d["light"].desired is False and d["light"].force


def test_bad_stored_times_fall_back_instead_of_crashing():
    from grow_brain.controller import parse_hhmm, valid_hhmm
    assert valid_hhmm("6:05") == "06:05" and valid_hhmm("18:00") == "18:00"
    for bad in ("6pm", "18.00", "06:00:00", "24:00", "", None, "7:5"):
        assert valid_hhmm(bad) is None
    assert parse_hhmm("6pm") == (6, 0) and parse_hhmm("bad", "08:00") == (8, 0)
    on, _ = light_window(datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc), "garbage", 18)
    assert on is True


def test_photoperiod_is_real_hours_across_dst():
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    # 2026-11-01: clocks go back at 02:00. Lights on 06:00 for 18 h → off at 00:00 local on 11-02 (still 18 real hours
    # after 06:00 EST... the day before had 06:00 EDT). Check both sides of the change stay 18 real hours.
    on, end = light_window(datetime(2026, 10, 31, 12, 0, tzinfo=ny), "06:00", 18)
    start = datetime(2026, 10, 31, 6, 0, tzinfo=ny)
    assert on and (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)) == timedelta(hours=18)
    # an on-time inside the repeated hour doesn't blink off
    on, _ = light_window(datetime(2026, 11, 1, 1, 45, fold=1, tzinfo=ny), "01:30", 18)
    assert on


def test_pause_ends_a_running_pulse_and_manual_exhaust_blocks_mist():
    ctx = _ctx(25.0, 50.0, paused=True, states={"humidifier": "on"}, on_tags={"humidifier": "humidifier"},
               switched={"humidifier": NOW - timedelta(seconds=30)})
    d = decide(ctx)
    assert d["humidifier"].desired is False and "paused" in d["humidifier"].reason
    # exhaust forced on by hand: the humidifier doesn't mist into it
    d = decide(_ctx(25.0, 48.0, overrides={"exhaust_fan": "on"}))
    assert d["humidifier"].desired is False and "waiting for the exhaust" in d["humidifier"].reason


def test_frozen_sensor_blocks_the_next_pulse():
    ctx = _ctx(25.0, 50.0, switched={"humidifier": NOW - timedelta(seconds=400)})
    ctx.sensor.updated_at = NOW - timedelta(seconds=600)     # no reading since the last pulse ended
    d = decide(ctx)
    assert d["humidifier"].desired is False and "fresh sensor reading" in d["humidifier"].reason


def test_humidity_run_does_not_latch_other_exhaust_runs_and_night_floor():
    # a cooling run ends with RH 1 point over max: it isn't kept running for humidity
    d = decide(_ctx(26.0, 66.0, states={"exhaust_fan": "on"}, on_tags={"exhaust_fan": "exhaust_cool"},
                    switched={"exhaust_fan": NOW - timedelta(minutes=8)}))
    assert d["exhaust_fan"].desired is False
    assert stage_defaults("veg").for_night().temp_min_c == 18.0
    dry = stage_defaults("drying")
    assert dry.for_night().temp_max_c == dry.temp_max_c      # no +1 °C when there's no night drop


def test_curing_leaves_the_humidifier_idle():
    assert decide(_ctx(20.0, 40.0, stage="curing"))["humidifier"].desired is False
