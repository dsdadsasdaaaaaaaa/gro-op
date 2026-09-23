"""The deterministic control loop.

Every `control_interval_s` seconds:
  1. read all HA states in one call
  2. pull the tent sensor values, compute VPD, store a reading
  3. work out what every mapped device *should* be doing (pure function `decide`)
  4. switch anything that differs, honouring manual overrides, pause, minimum switch intervals
     and hard safety limits
Claude never touches devices directly; it can only nudge the target bands within safe bounds.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .devices import ROLE_BY_NAME, SWITCH_ROLES
from .ha import HAClient
from .store import Store, iso, parse_iso, utcnow
from .targets import Targets, apply_overrides, days_between, f_to_c, stage_defaults, vpd_kpa

log = logging.getLogger(__name__)

POWER_SUFFIXES = ("_current_consumption", "_power", "_current_power", "_active_power", "_watts")
ENERGY_TODAY_SUFFIXES = ("_today_s_consumption", "_today_consumption", "_energy_today", "_today_energy")
ENERGY_MONTH_SUFFIXES = ("_this_month_s_consumption", "_month_consumption", "_energy_month")
ENERGY_TOTAL_SUFFIXES = ("_energy", "_total_energy", "_energy_total", "_total_consumption")  # cumulative meters (Matter, Shelly...)
LOW_POWER_W = {"light": 15.0, "exhaust_fan": 3.0, "intake_fan": 2.0, "circulation_fan": 2.0, "circulation_fan_2": 2.0,
               "humidifier": 3.0, "dehumidifier": 20.0, "heater": 20.0, "cooler": 30.0}
POWER_GRACE_S = 180

TEMP_HYST = 1.0      # °C
RH_HYST = 4.0        # % RH (dehumidifier)
LAG_S = 300              # the tent sensor reports a change 2-5 min after it happens: pulse, then wait this long
HUM_GAIN_DEFAULT = 1.5   # % RH per minute of humidifier; learned from every pulse
COOL_GAIN_DEFAULT = 0.25  # °C per minute of exhaust; learned from every cooling pulse
HUM_PULSE_S = (60, 300)   # shortest / longest humidifier pulse
COOL_PULSE_S = (120, 360)  # shortest / longest exhaust cooling pulse
WAY_TOO_HOT_C = 1.5       # this far above max the exhaust runs continuously instead of pulsing
RH_EXHAUST_MARGIN = 3.0   # exhaust only dumps humidity this far above the max (mist settles on its own)
DUTY_SKIP_S = 600         # skip a scheduled air exchange if the exhaust ran (for any reason) within this long
UNAVAILABLE_ALERT_S = 180  # a mapped plug unreachable this long gets its own alert
LOOP_FAIL_ALERT = 5        # consecutive failed control cycles before an alert
LATCH_MIN_S = 900          # a tripped hard limit holds at least this long
CLIMATE_CHECK_S = 600     # how often to ask "can this tent actually hold its targets?"
CLIMATE_DUTY_LIMIT = 0.40  # exhaust on more than this share of the last hour = the light is too hot for the band
RH_CRITICAL = 85.0   # bud-rot territory; always dehumidify/exhaust above this
STALE_AFTER_S = 30 * 60
EXHAUST_DUTY_ON_MIN = 5
EXHAUST_DUTY_PERIOD_MIN = 20
EXHAUST_DUTY_SEEDLING = (3, 30)  # seedlings use little CO2; fewer pulses keep humidity up


@dataclass
class SensorSnapshot:
    temp_c: Optional[float] = None
    humidity: Optional[float] = None
    vpd_kpa: Optional[float] = None
    co2: Optional[float] = None
    updated_at: Optional[datetime] = None
    stale: bool = True

    def to_api(self) -> dict:
        from .targets import c_to_f
        return {
            "temp_c": self.temp_c,
            "temp_f": c_to_f(self.temp_c) if self.temp_c is not None else None,
            "humidity": self.humidity,
            "vpd_kpa": self.vpd_kpa,
            "co2": self.co2,
            "updated_at": iso(self.updated_at),
            "stale": self.stale,
        }


@dataclass
class DeviceInput:
    role: str
    entity_id: Optional[str]
    state: Optional[str]        # "on" | "off" | None
    available: bool
    last_switched: Optional[datetime]
    override_mode: Optional[str]  # "on" | "off" | None
    override_until: Optional[str]
    on_reading: Optional[float] = None   # RH (humidifier) or °C (exhaust) when the controller switched it on
    on_tag: Optional[str] = None         # what the controller switched it on for ("humidifier", "exhaust_cool", "exhaust_duty"...)


@dataclass
class Decision:
    role: str
    desired: Optional[bool]  # None = leave as is
    reason: str
    force: bool = False
    tag: Optional[str] = None  # pulse bookkeeping: "<what>" when starting a pulse, "<what>_done" when ending one


@dataclass
class ControlContext:
    now_local: datetime
    stage: str
    targets: Targets            # the band in force right now (day or night)
    day_targets: Targets
    light_scheduled_on: bool
    lights_on: bool             # actual (or scheduled if unknown)
    sensor: SensorSnapshot
    safety_temp_max_c: float
    safety_temp_min_c: float
    exhaust_ducted: bool
    paused: bool
    devices: dict[str, DeviceInput] = field(default_factory=dict)
    standby: bool = False
    hum_gain: float = HUM_GAIN_DEFAULT    # learned humidifier strength, % RH per minute
    cool_gain: float = COOL_GAIN_DEFAULT  # learned exhaust cooling, °C per minute
    safety_latch: Optional[str] = None    # "hot" / "cold": a hard limit tripped and the tent hasn't recovered yet


# ---------------------------------------------------------------- times of day

def valid_hhmm(s) -> Optional[str]:
    """'6:05' / '06:05' → '06:05'; anything else → None."""
    if not isinstance(s, str):
        return None
    parts = s.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (1 <= len(parts[0]) <= 2) or len(parts[1]) != 2:
        return None
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return f"{hh:02d}:{mm:02d}"


def parse_hhmm(s, default: str = "06:00") -> tuple[int, int]:
    """Hours and minutes from a stored time; a bad value falls back to the default instead of stopping the loop."""
    v = valid_hhmm(s) or default
    hh, mm = v.split(":")
    return int(hh), int(mm)


# ---------------------------------------------------------------- light schedule

def light_window(now_local: datetime, on_time: str, hours: float) -> tuple[bool, datetime]:
    """Return (should_be_on, next_change_local)."""
    if hours <= 0:
        return False, now_local + timedelta(days=365)
    if hours >= 24:
        return True, now_local + timedelta(days=365)
    hh, mm = parse_hhmm(on_time)
    today_on = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    # Find the most recent "on" moment at or before now.
    start = today_on if today_on <= now_local else today_on - timedelta(days=1)
    end = start + timedelta(hours=hours)
    if now_local < end:
        return True, end
    return False, start + timedelta(days=1)


# ---------------------------------------------------------------- pure decision logic

def decide(ctx: ControlContext) -> dict[str, Decision]:
    d: dict[str, Decision] = {}
    s = ctx.sensor
    t = ctx.targets
    temp, rh = s.temp_c, s.humidity
    have = lambda r: r in ctx.devices and ctx.devices[r].entity_id
    is_on = lambda r: ctx.devices[r].state == "on" if have(r) else False

    def set_(role, desired, reason, force=False, tag=None):
        if have(role):
            d[role] = Decision(role, desired, reason, force, tag)

    fresh = not s.stale and temp is not None and rh is not None
    hot = ctx.safety_latch == "hot" or (fresh and temp >= ctx.safety_temp_max_c)
    cold = not hot and (ctx.safety_latch == "cold" or (fresh and temp <= ctx.safety_temp_min_c))
    rh_critical = fresh and rh >= RH_CRITICAL

    # --- standby: nothing planted, everything off; manual overrides still respected,
    #     except that the hard limits below still win (a light switched on by hand can't cook a closed tent) ---
    if ctx.standby:
        for role in ctx.devices:
            set_(role, False, "tent in standby")
        if hot:
            _hot_safety(ctx, set_, temp)
        elif rh_critical:
            set_("exhaust_fan", True, f"SAFETY: RH {rh:.0f}% critical, exhaust on", force=True)
            set_("humidifier", False, "SAFETY: RH critical", force=True)
        elif cold:
            set_("humidifier", False, "SAFETY: too cold", force=True)
        return _apply_overrides_and_pause(ctx, d)

    # --- an overheat cut stays in force until the tent has really cooled, even if the sensor drops out ---
    if hot and not fresh:
        for r in ("circulation_fan", "circulation_fan_2"):
            set_(r, True, "constant air movement")
        _hot_safety(ctx, set_, temp)
        return _apply_overrides_and_pause(ctx, d)

    # --- light: schedule ---
    if ctx.stage in ("drying", "curing", "done"):
        set_("light", False, f"{ctx.stage}: lights stay off")
    else:
        set_("light", ctx.light_scheduled_on,
             f"schedule {t.light_hours:g}h from {t.light_on_time}: " + ("on" if ctx.light_scheduled_on else "off"))

    # --- circulation: always on while growing/drying ---
    circ_on = ctx.stage not in ("curing", "done")
    for r in ("circulation_fan", "circulation_fan_2"):
        set_(r, circ_on, "constant air movement" if circ_on else f"{ctx.stage}: not needed")

    # --- sensor missing / stale: safe mode ---
    if s.stale or temp is None or rh is None:
        set_("exhaust_fan", True, "sensor stale: exhaust on to be safe")
        set_("intake_fan", True, "sensor stale: with exhaust")
        for r in ("humidifier", "dehumidifier", "heater", "cooler"):
            set_(r, False, "sensor stale: off to be safe")
        return _apply_overrides_and_pause(ctx, d)

    # --- hard safety limits (bypass overrides, pause and switch intervals) ---
    if hot:
        _hot_safety(ctx, set_, temp)
        return _apply_overrides_and_pause(ctx, d)
    if cold:
        set_("heater", True, f"SAFETY: {temp:.1f}°C ≤ {ctx.safety_temp_min_c:g}°C, heater on", force=True)
        set_("cooler", False, "SAFETY: too cold", force=True)
        set_("exhaust_fan", rh >= RH_CRITICAL, "SAFETY: too cold, exhaust off" if rh < RH_CRITICAL else "RH critical", force=True)
        set_("intake_fan", rh >= RH_CRITICAL, "SAFETY: too cold", force=True)
        set_("humidifier", False, "SAFETY: too cold", force=True)
        return _apply_overrides_and_pause(ctx, d)

    # --- temperature ---
    too_hot = temp > t.temp_max_c or (is_on("cooler") and temp > t.temp_max_c - TEMP_HYST)
    too_cold = temp < t.temp_min_c or (is_on("heater") and temp < t.temp_min_c + TEMP_HYST)
    # --- humidity ---
    too_humid = rh > t.humidity_max or (is_on("dehumidifier") and rh > t.humidity_max - RH_HYST)

    # --- exhaust: cooling pulses, humidity dump, plus a baseline air-exchange duty while lights on ---
    exhaust_humid = rh > t.humidity_max + RH_EXHAUST_MARGIN or (is_on("exhaust_fan") and rh > t.humidity_max)
    duty_on, duty_period = EXHAUST_DUTY_SEEDLING if ctx.stage == "seedling" else (EXHAUST_DUTY_ON_MIN, EXHAUST_DUTY_PERIOD_MIN)
    minute_of_period = (ctx.now_local.hour * 60 + ctx.now_local.minute) % duty_period
    growing = ctx.stage not in ("curing", "done")
    ex = ctx.devices.get("exhaust_fan")
    # A cooling pulse already exchanged the air: don't dump the humidity a second time.
    recently_ran = ex is not None and ex.last_switched is not None and \
        (ctx.now_local - ex.last_switched).total_seconds() < DUTY_SKIP_S
    duty_window = ctx.lights_on and minute_of_period < duty_on and growing
    duty = duty_window and ((is_on("exhaust_fan") and ex is not None and ex.on_tag == "exhaust_duty") or not recently_ran)
    ducted_note = "" if ctx.exhaust_ducted else " (not ducted outside yet: limited effect)"
    cooling = temp > t.temp_max_c or (is_on("exhaust_fan") and ex is not None and ex.on_tag == "exhaust_cool")
    cool = None
    if cooling and ex is not None and temp < t.temp_max_c + WAY_TOO_HOT_C:
        start_temp = ex.on_reading if ex.on_reading is not None else temp
        cool = _pulse(ex, ctx.now_local, temp - t.temp_max_c + 0.5, start_temp - t.temp_max_c + 0.5,
                      ctx.cool_gain, COOL_PULSE_S, "exhaust_cool")
    if rh >= RH_CRITICAL:
        set_("exhaust_fan", True, f"RH {rh:.1f}% critical, exhaust on" + ducted_note, force=True)
    elif temp >= t.temp_max_c + WAY_TOO_HOT_C:
        set_("exhaust_fan", True, f"{temp:.1f}°C far above max {t.temp_max_c:g}°C, exhaust on" + ducted_note, tag="exhaust_cool")
    elif cool is not None and (cool[0] or not (exhaust_humid or duty)):
        set_("exhaust_fan", cool[0], f"{temp:.1f}°C vs max {t.temp_max_c:g}°C: " + cool[1] + ducted_note, tag=cool[2])
    elif exhaust_humid:
        set_("exhaust_fan", True, f"RH {rh:.1f}% above max {t.humidity_max:g}%" + ducted_note)
    elif too_cold and not too_humid:
        set_("exhaust_fan", False, f"{temp:.1f}°C below min {t.temp_min_c:g}°C, keeping heat in")
    elif duty:
        set_("exhaust_fan", True, f"fresh-air exchange ({duty_on} min every {duty_period})", tag="exhaust_duty")
    else:
        set_("exhaust_fan", False, f"{temp:.1f}°C / {rh:.1f}% RH within targets")
    if "exhaust_fan" in d:
        set_("intake_fan", d["exhaust_fan"].desired, "follows exhaust")

    # --- cooler / heater ---
    if too_hot:
        set_("cooler", True, f"{temp:.1f}°C above max {t.temp_max_c:g}°C")
        set_("heater", False, "too warm")
    elif too_cold:
        set_("heater", True, f"{temp:.1f}°C below min {t.temp_min_c:g}°C")
        set_("cooler", False, "too cold")
    else:
        set_("cooler", False, f"{temp:.1f}°C within {t.temp_min_c:g}–{t.temp_max_c:g}°C")
        set_("heater", False, f"{temp:.1f}°C within {t.temp_min_c:g}–{t.temp_max_c:g}°C")

    # --- humidity devices ---
    if rh >= RH_CRITICAL:
        set_("dehumidifier", True, f"RH {rh:.1f}% critical", force=True)
        set_("humidifier", False, "RH critical", force=True)
    elif too_humid:
        set_("dehumidifier", True, f"RH {rh:.1f}% above max {t.humidity_max:g}%")
        set_("humidifier", False, "too humid")
    else:
        set_("dehumidifier", False, f"RH {rh:.1f}% within {t.humidity_min:g}–{t.humidity_max:g}%")
        # Humidifier: pulse, then wait for the slow sensor, topping up to just inside the band.
        # (No pre-loading before an air exchange: the exchange replaces the tent air, so that water goes straight out.)
        start_below, target, why = t.humidity_min + 1.0, t.humidity_min + 2.0, "below min"
        hum = ctx.devices.get("humidifier")
        exhaust_now = d["exhaust_fan"].desired if "exhaust_fan" in d and d["exhaust_fan"].desired is not None else is_on("exhaust_fan")
        if hum is None or not hum.entity_id:
            pass
        elif is_on("humidifier") and rh >= target:
            set_("humidifier", False, f"RH {rh:.1f}% reached {target:g}%", tag="humidifier_done")
        elif not is_on("humidifier") and rh < start_below and exhaust_now:
            # mist into an exhausting tent goes straight outside; wait for the pulse to end
            set_("humidifier", False, f"RH {rh:.1f}% {why}: waiting for the exhaust to finish")
        elif rh < start_below or is_on("humidifier"):
            start_rh = hum.on_reading if hum.on_reading is not None else rh
            on, note, tag = _pulse(hum, ctx.now_local, target - rh, target - start_rh, ctx.hum_gain, HUM_PULSE_S, "humidifier")
            set_("humidifier", on, f"RH {rh:.1f}% {why} ({note})", tag=tag)
        else:
            set_("humidifier", False, f"RH {rh:.1f}% within {t.humidity_min:g}–{t.humidity_max:g}%")

    return _apply_overrides_and_pause(ctx, d)


def _hot_safety(ctx: ControlContext, set_, temp: Optional[float]) -> None:
    now = f"{temp:.1f}°C" if temp is not None else "sensor not reporting"
    why = f"SAFETY: overheat cut ({now}; holds until the tent cools to {min(ctx.day_targets.temp_max_c, ctx.safety_temp_max_c - 3):g}°C)"
    set_("light", False, why + ", lights off", force=True)
    set_("exhaust_fan", True, why + ", exhaust on", force=True)
    set_("intake_fan", True, why + ", intake on", force=True)
    set_("cooler", True, why, force=True)
    set_("heater", False, why, force=True)
    set_("humidifier", False, why, force=True)
    set_("dehumidifier", False, why + " (a dehumidifier adds heat)", force=True)


def _pulse(dev: DeviceInput, now: datetime, deficit_now: float, deficit_at_start: float, gain_per_min: float,
           bounds: tuple[int, int], what: str) -> tuple[bool, str, Optional[str]]:
    """Run a device for a pulse sized to the deficit, then rest LAG_S so the slow sensor can report the
    effect before deciding again. Returns (desired, note, tag)."""
    lo, hi = bounds
    gain = max(gain_per_min, 0.01)
    if dev.state == "on":
        if dev.last_switched is None:
            return False, "ending the pulse that was running before the restart", f"{what}_done"
        planned = max(lo, min(hi, deficit_at_start / gain * 60.0))
        elapsed = (now - dev.last_switched).total_seconds()
        if elapsed >= planned:
            return False, f"{planned:.0f} s pulse done, waiting for the sensor", f"{what}_done"
        return True, f"pulse {elapsed:.0f}/{planned:.0f} s", what
    if dev.last_switched is not None and (now - dev.last_switched).total_seconds() < LAG_S:
        return False, "resting until the sensor catches up", None
    planned = max(lo, min(hi, deficit_now / gain * 60.0))
    return True, f"{planned:.0f} s pulse", what


def learn_gain(current: Optional[float], sample: float, low: float, high: float) -> Optional[float]:
    """Blend a measured response into the learned gain; ignore samples outside the plausible range."""
    if not (low <= sample <= high):
        return current
    if current is None:
        return round(sample, 3)
    return round(0.7 * current + 0.3 * sample, 3)


def _apply_overrides_and_pause(ctx: ControlContext, d: dict[str, Decision]) -> dict[str, Decision]:
    for role, dec in list(d.items()):
        dev = ctx.devices.get(role)
        if dev is None:
            continue
        if dec.force:
            continue  # safety wins over everything
        if dev.override_mode in ("on", "off"):
            until = f" until {dev.override_until[11:16]} UTC" if dev.override_until else ""
            d[role] = Decision(role, dev.override_mode == "on", f"manual override: {dev.override_mode}{until}")
        elif ctx.paused:
            d[role] = Decision(role, None, "automation paused")
    return d


# ---------------------------------------------------------------- the runtime

class Controller:
    def __init__(self, store: Store, ha: HAClient, boot_tz: str, notifier):
        self.store = store
        self.ha = ha
        self.notifier = notifier
        self.boot_tz = boot_tz
        self.last_switched: dict[str, datetime] = {}
        self.last_reasons: dict[str, str] = {}
        self.sensor = SensorSnapshot()
        self.states: dict[str, dict] = {}
        self.ha_ok = False
        self._ha_fail_reported = False
        self._stale_reported = False
        self._safety_reported: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self.last_cycle_at: Optional[datetime] = None
        self._on_since: dict[str, datetime] = {}
        self._power_warned: dict[str, datetime] = {}
        self._energy_baselines: dict[tuple[str, str], float] = {}
        self.on_reading: dict[str, float] = {}
        self.on_tag: dict[str, str] = {}
        self.learned: dict = {}            # {"humidifier_pts_per_min": x, "exhaust_c_per_min": y}
        self._pending_samples: list[dict] = []
        self._restored = False
        self._climate_checked_at: Optional[datetime] = None
        self._climate_alert = False
        self._tank: Optional[dict] = None   # humidifier water: run seconds since the last refill, open task id
        self.safety_latch: Optional[dict] = None   # {"kind": "hot"|"cold", "since": iso}
        self._unavail_since: dict[str, datetime] = {}
        self._unavail_alerted: set[str] = set()
        self._last_known: dict[str, str] = {}
        self._cmd: dict[str, dict] = {}          # role → {"desired": bool, "tries": n} while a command hasn't taken effect
        self._cmd_alerted: set[str] = set()
        self._safety_kind: Optional[str] = None
        self.started_at = utcnow()
        self.last_attempt_at: Optional[datetime] = None
        self.consecutive_failures = 0
        self.last_error: Optional[str] = None
        self._loop_alerted = False

    # ---- config helpers (read from store each cycle so app changes apply immediately) ----
    async def settings(self) -> dict:
        s = await self.store.get_kv("settings", {}) or {}
        s.setdefault("timezone", self.boot_tz)
        s.setdefault("safety_temp_max_c", 35.0)
        s.setdefault("safety_temp_min_c", 12.0)
        s.setdefault("control_interval_s", 30)
        s.setdefault("min_switch_interval_s", 180)
        s.setdefault("humidifier_tank_hours", 4.0)   # hours of misting one tank lasts at the knob setting in use
        s.setdefault("auto_apply_advisor_targets", True)
        s.setdefault("units", "c")
        s.setdefault("brief_time", "08:00")
        defaults = {"safety_temp_max_c": 35.0, "safety_temp_min_c": 12.0, "control_interval_s": 30,
                    "min_switch_interval_s": 180, "humidifier_tank_hours": 4.0, "brief_time": "08:00", "units": "c"}
        for k, v in defaults.items():
            if s.get(k) is None:
                s[k] = v

        def clamp(k, lo, hi, cast=float):
            try:
                s[k] = cast(min(hi, max(lo, float(s[k]))))
            except (TypeError, ValueError):
                s[k] = defaults[k]
        clamp("safety_temp_max_c", 28.0, 40.0)
        clamp("safety_temp_min_c", 5.0, 20.0)
        clamp("control_interval_s", 10, 300, int)
        clamp("min_switch_interval_s", 30, 3600, int)
        clamp("humidifier_tank_hours", 0.5, 48.0)
        s["brief_time"] = valid_hhmm(s.get("brief_time")) or "08:00"
        return s

    def tz(self, settings: dict) -> ZoneInfo:
        name = settings.get("timezone") or self.boot_tz
        try:
            return ZoneInfo(name)
        except Exception:
            if not getattr(self, "_tz_warned", False):
                log.warning("Unknown timezone %r: using UTC. Use a name like America/New_York.", name)
                self._tz_warned = True
            return ZoneInfo("UTC")

    async def profile(self) -> dict:
        from .models import GrowProfile
        raw = await self.store.get_kv("grow_profile", None)
        return GrowProfile(**raw).model_dump() if raw else GrowProfile().model_dump()

    async def effective_targets(self, profile: dict | None = None, settings: dict | None = None) -> tuple[Targets, int, int]:
        """Day-band targets plus day counters (day_in_stage, day_total)."""
        profile = profile or await self.profile()
        settings = settings or await self.settings()
        today = datetime.now(self.tz(settings)).date()
        start = _pdate(profile.get("start_date"))
        stage_started = _pdate(profile.get("stage_started")) or start
        day_in_stage = days_between(stage_started, today)
        day_total = days_between(start, today)
        override = await self.store.get_kv("targets_override", None)
        base = stage_defaults(profile["stage"], day_in_stage, valid_hhmm((override or {}).get("light_on_time")) or "06:00")
        if override:
            base = apply_overrides(base, override.get("values", {}), override.get("source", "manual"))
        return base, day_in_stage, day_total

    async def standby(self) -> bool:
        return bool(await self.store.get_kv("standby", False))

    async def paused_until(self) -> Optional[str]:
        p = await self.store.get_kv("control_paused_until", None)
        if p and (parse_iso(p) or utcnow()) > utcnow():
            return p
        return None

    # ---- per-cycle ----
    async def build_context(self) -> ControlContext:
        settings = await self.settings()
        profile = await self.profile()
        tz = self.tz(settings)
        now_local = datetime.now(tz)
        day_targets, _, _ = await self.effective_targets(profile, settings)
        scheduled_on, _ = light_window(now_local, day_targets.light_on_time, day_targets.light_hours)

        dmap = await self.store.get_device_map()
        overrides = await self.store.get_overrides()
        devices: dict[str, DeviceInput] = {}
        for role in SWITCH_ROLES:
            eid = dmap.get(role)
            st = self.states.get(eid) if eid else None
            state = st["state"] if st and st["state"] in ("on", "off") else None
            ov = overrides.get(role)
            devices[role] = DeviceInput(
                role, eid, state, bool(st) and st["state"] not in ("unavailable", "unknown"),
                self.last_switched.get(role), ov["mode"] if ov else None, ov["until"] if ov else None,
                self.on_reading.get(role), self.on_tag.get(role),
            )
        light_state = devices["light"].state if devices.get("light") else None
        lights_on = light_state == "on" if light_state is not None else scheduled_on
        targets = day_targets if lights_on else day_targets.for_night()
        return ControlContext(
            now_local=now_local, stage=profile["stage"], targets=targets, day_targets=day_targets,
            light_scheduled_on=scheduled_on, lights_on=lights_on, sensor=self.sensor,
            hum_gain=float(self.learned.get("humidifier_pts_per_min") or HUM_GAIN_DEFAULT),
            cool_gain=float(self.learned.get("exhaust_c_per_min") or COOL_GAIN_DEFAULT),
            safety_temp_max_c=float(settings["safety_temp_max_c"]), safety_temp_min_c=float(settings["safety_temp_min_c"]),
            exhaust_ducted=bool(profile.get("exhaust_ducted")), paused=bool(await self.paused_until()),
            devices=devices, standby=await self.standby(),
            safety_latch=(self.safety_latch or {}).get("kind"),
        )

    def _read_sensors(self, dmap: dict[str, str]) -> SensorSnapshot:
        snap = SensorSnapshot()
        newest: Optional[datetime] = None

        def num(role):
            nonlocal newest
            eid = dmap.get(role)
            st = self.states.get(eid) if eid else None
            if not st or st["state"] in ("unavailable", "unknown", "", None):
                return None, None
            try:
                v = float(st["state"])
            except (TypeError, ValueError):
                return None, None
            ts = parse_iso(st.get("last_reported") or st.get("last_updated"))
            if ts and (newest is None or ts > newest):
                newest = ts
            return v, st.get("attributes", {}).get("unit_of_measurement")

        t, unit = num("temperature_sensor")
        if t is not None and unit and "F" in unit:
            t = f_to_c(t)
        h, _ = num("humidity_sensor")
        off = getattr(self, "_offsets", (0.0, 0.0))
        if t is not None:
            t += off[0]
        if h is not None:
            h = min(100.0, max(0.0, h + off[1]))
        v, _ = num("vpd_sensor")
        c, _ = num("co2_sensor")
        snap.temp_c = round(t, 1) if t is not None else None
        snap.humidity = round(h, 1) if h is not None else None
        snap.co2 = c
        if v is not None:
            snap.vpd_kpa = round(v, 2)
        elif t is not None and h is not None:
            snap.vpd_kpa = vpd_kpa(t, h)
        snap.updated_at = newest
        age_ok = newest is not None and (utcnow() - newest).total_seconds() < STALE_AFTER_S
        snap.stale = not (age_ok and snap.temp_c is not None and snap.humidity is not None)
        return snap

    async def _safe(self, coro, what: str):
        """Run one bookkeeping step; a failure (full disk, locked database...) is logged, never fatal to switching."""
        try:
            return await coro
        except Exception as e:
            log.exception("%s failed", what)
            self.last_error = f"{what}: {e}"
            return None

    async def cycle(self) -> None:
        try:
            states = await self.ha.get_states()
        except Exception as e:
            self.ha_ok = False
            if not self._ha_fail_reported:
                self._ha_fail_reported = True
                await self._safe(self.notifier.send("ha_down", f"Grow Brain can't reach Home Assistant ({e}). The tent isn't being controlled.",
                                                    hours=6, everyone=True), "notify")
                await self._safe(self.store.add_event("alert", "system", f"Cannot reach Home Assistant: {e}"), "event")
            return
        if self._ha_fail_reported:
            await self._safe(self.store.add_event("info", "system", "Home Assistant connection restored"), "event")
            self._ha_fail_reported = False
        if not self.ha_ok:
            # first good cycle since startup (or since an outage): any older "cannot reach" alert is over
            await self._safe(self.store.resolve_alerts("system", "Cannot reach Home Assistant"), "resolve")
        self.ha_ok = True
        self.states = {s["entity_id"]: s for s in states}

        dmap = await self.store.get_device_map()
        _s = await self.settings()
        self._offsets = (float(_s.get("temp_offset_c") or 0.0), float(_s.get("humidity_offset") or 0.0))
        self.sensor = self._read_sensors(dmap)
        if not self._restored:
            await self._restore_switch_times()
        await self._update_latch(_s, dmap)
        ctx = await self.build_context()

        # 1. decide and switch before any bookkeeping, so a database problem can never stop a safety action
        decisions = decide(ctx)
        results = await self._switch(ctx, decisions, _s)

        # 2. tell people, then record
        await self._safe(self._report_safety(ctx, decisions, results), "safety report")
        await self._safe(self._report_stale(dmap, ctx.standby), "stale report")
        await self._safe(self._report_unavailable(ctx, dmap), "unavailable report")
        if not self.sensor.stale:
            await self._safe(self.store.add_reading(self.sensor.temp_c, self.sensor.humidity, self.sensor.vpd_kpa,
                                                    self.sensor.co2, ctx.lights_on), "reading")
        self._last_lights_on = ctx.lights_on
        await self._safe(self._learn(ctx), "learning")
        await self._safe(self._power_watchdog(dmap), "power watchdog")
        await self._safe(self._update_energy_baselines(dmap, ctx.now_local), "energy")
        await self._safe(self._climate_check(ctx), "climate check")
        await self._safe(self._tank_tracker(ctx), "tank")
        self.last_cycle_at = utcnow()

    async def _switch(self, ctx: ControlContext, decisions: dict[str, Decision], settings: dict) -> dict[str, str]:
        """Apply decisions. Returns role → 'switched' | 'already' | 'failed' | 'unavailable' | 'waiting' | 'unmapped'."""
        results: dict[str, str] = {}
        min_iv = int(settings["min_switch_interval_s"])
        now = utcnow()
        for role, dec in decisions.items():
            dev = ctx.devices[role]
            self.last_reasons[role] = dec.reason
            if dev.state in ("on", "off"):
                self._last_known[role] = dev.state
            if dec.desired is None:
                continue
            if not dev.entity_id:
                results[role] = "unmapped"
                continue
            if not dev.available:
                results[role] = "unavailable"
                self.last_reasons[role] = "plug not responding in Home Assistant"
                continue
            want = "on" if dec.desired else "off"
            if dev.state == want:
                results[role] = "already"
                if self._cmd.pop(role, None) is not None and role in self._cmd_alerted:
                    self._cmd_alerted.discard(role)
                    await self._safe(self.store.resolve_alerts("device", f"{ROLE_BY_NAME[role].label} isn't responding"), "resolve")
                continue
            iv = max(min_iv, 300) if role in ("dehumidifier", "cooler") else min_iv
            if role == "humidifier":
                iv = min(iv, 60)  # an ultrasonic humidifier is happy to pulse; this is what makes the pulses short
            last = self.last_switched.get(role)
            if last and not dec.force and (now - last).total_seconds() < iv:
                self.last_reasons[role] = dec.reason + " (waiting for minimum switch interval)"
                results[role] = "waiting"
                continue
            ok = await self.ha.turn(dev.entity_id, dec.desired)
            # Home Assistant often answers 200 for a plug that is really offline: count a command that
            # never takes effect as a failure too.
            cmd = self._cmd.get(role)
            tries = (cmd["tries"] + 1) if cmd and cmd["desired"] == dec.desired else 1
            self._cmd[role] = {"desired": dec.desired, "tries": tries}
            if not ok or tries >= 3:
                results[role] = "failed"
                if role not in self._cmd_alerted and (tries >= 3 or (not ok and tries >= 2)):
                    self._cmd_alerted.add(role)
                    label = ROLE_BY_NAME[role].label
                    msg = (f"{label} isn't responding: Grow Brain has tried to switch it {want.upper()} {tries} times "
                           f"({dec.reason}). Check its plug" + (", and switch it off by hand if it's running." if want == "off" else "."))
                    await self._safe(self.notifier.send(f"cmd:{role}", msg, hours=2, everyone=True), "notify")
                    await self._safe(self.store.add_event("alert" if dec.force else "warn", "device", msg), "event")
            else:
                results[role] = "switched"
            if ok:
                self._note_switch(role, dec, ctx, last, now)
                self.last_switched[role] = now
                # optimistic local state so the next cycle's hysteresis sees it
                self.states.setdefault(dev.entity_id, {})["state"] = want
                await self._safe(self.store.log_device(role, want, dec.reason), "device log")
                await self._safe(self.store.add_event("info", "device",
                                                      f"{ROLE_BY_NAME[role].label} → {want.upper()}: {dec.reason}"), "event")
        return results

    async def _update_latch(self, settings: dict, dmap: dict[str, str]) -> None:
        """Trip on a hard limit; release only after the tent has recovered with margin and some time has passed."""
        if self.safety_latch is None and not getattr(self, "_latch_loaded", False):
            self._latch_loaded = True
            self.safety_latch = await self._safe(self.store.get_kv("safety_latch", None), "latch load")
        s = self.sensor
        if s.stale or s.temp_c is None:
            return
        hi, lo = float(settings["safety_temp_max_c"]), float(settings["safety_temp_min_c"])
        now = utcnow()
        latch = self.safety_latch
        if s.temp_c >= hi and (not latch or latch.get("kind") != "hot"):
            self.safety_latch = {"kind": "hot", "since": iso(now)}
        elif s.temp_c <= lo and not latch:
            self.safety_latch = {"kind": "cold", "since": iso(now)}
        elif latch:
            since = parse_iso(latch.get("since")) or now
            held = (now - since).total_seconds() >= LATCH_MIN_S
            if latch.get("kind") == "hot":
                profile = await self.profile()
                day, _, _ = await self.effective_targets(profile, settings)
                release_at = min(day.temp_max_c, hi - 3.0)
                if held and s.temp_c <= release_at:
                    self.safety_latch = None
            elif latch.get("kind") == "cold" and held and s.temp_c >= lo + 2.0:
                self.safety_latch = None
        if self.safety_latch != latch:
            await self._safe(self.store.set_kv("safety_latch", self.safety_latch), "latch save")

    async def _report_stale(self, dmap: dict[str, str], standby: bool = False) -> None:
        if self.sensor.stale and not self._stale_reported and dmap.get("temperature_sensor"):
            self._stale_reported = True
            what = "" if standby else " Automation is in safe mode (exhaust on, humidifier off)."
            await self.notifier.send("stale", "The tent sensor has stopped reporting." + what +
                                     " Check the Govee sensor's batteries and that it's in range of its hub.",
                                     hours=6, everyone=True)
            await self.store.add_event("warn", "safety", "Tent sensor is stale or unavailable. Running in safe mode (exhaust on, climate devices off).")
        elif not self.sensor.stale and self._stale_reported:
            self._stale_reported = False
            await self.store.add_event("info", "safety", "Tent sensor is reporting again.")
            await self.store.resolve_alerts("safety", "Tent sensor is stale")

    async def _report_unavailable(self, ctx: ControlContext, dmap: dict[str, str]) -> None:
        now = utcnow()
        for role in SWITCH_ROLES:
            eid = dmap.get(role)
            dev = ctx.devices.get(role)
            if not eid or dev is None:
                continue
            if dev.available:
                self._unavail_since.pop(role, None)
                if role in self._unavail_alerted:
                    self._unavail_alerted.discard(role)
                    await self.store.resolve_alerts("device", f"{ROLE_BY_NAME[role].label} plug")
                    await self.store.add_event("info", "device", f"{ROLE_BY_NAME[role].label} plug is responding again.")
                continue
            since = self._unavail_since.setdefault(role, now)
            if role in self._unavail_alerted or (now - since).total_seconds() < UNAVAILABLE_ALERT_S:
                continue
            self._unavail_alerted.add(role)
            label = ROLE_BY_NAME[role].label
            if eid not in self.states:
                msg = (f"{label} plug ({eid}) no longer exists in Home Assistant, so Grow Brain can't switch it. "
                       f"It may have been renamed or re-paired: ask Levi to check.")
            else:
                last = self._last_known.get(role)
                msg = f"{label} plug isn't responding in Home Assistant, so Grow Brain can't switch it."
                if last == "on":
                    msg += " It was last ON: switch it off at the plug by hand until it's back."
                elif last == "off":
                    msg += " It was last off."
            await self.notifier.send(f"unavailable:{role}", msg, hours=6, everyone=True)
            await self.store.add_event("alert" if role in ("light", "humidifier") else "warn", "device", msg)

    # ---- pulse learning: how strong are the humidifier and the exhaust in *this* tent? ----
    def _note_switch(self, role: str, dec: Decision, ctx: ControlContext, on_at: Optional[datetime], now: datetime) -> None:
        reading = self.sensor.humidity if role == "humidifier" else self.sensor.temp_c
        if dec.desired:
            if reading is not None:
                self.on_reading[role] = reading
            if dec.tag:
                self.on_tag[role] = dec.tag
            return
        start = self.on_reading.pop(role, None)
        tag = self.on_tag.pop(role, None)
        if dec.tag in ("humidifier_done", "exhaust_cool_done") and start is not None and on_at is not None \
                and tag in ("humidifier", "exhaust_cool"):
            minutes = (now - on_at).total_seconds() / 60.0
            if minutes >= 0.5:
                self._pending_samples.append({
                    "role": role, "start": start, "minutes": minutes, "on_at": on_at, "ended": now,
                    "lights_on": ctx.lights_on,
                })

    async def _learn(self, ctx: ControlContext) -> None:
        if not self._pending_samples or self.sensor.stale:
            return
        now = utcnow()
        keep = []
        changed = False
        for smp in self._pending_samples:
            if (now - smp["ended"]).total_seconds() < LAG_S:
                keep.append(smp)
                continue
            if smp["role"] == "humidifier":
                ex_last = self.last_switched.get("exhaust_fan")
                if ex_last and ex_last > smp["on_at"] or self.sensor.humidity is None:
                    continue  # the exhaust ran during the window: not a clean measurement
                sample = (self.sensor.humidity - smp["start"]) / smp["minutes"]
                key, lo, hi, label = "humidifier_pts_per_min", 0.2, 6.0, "humidifier raises humidity about %.1f points per minute"
            else:
                if ctx.lights_on != smp["lights_on"] or self.sensor.temp_c is None:
                    continue
                sample = (smp["start"] - self.sensor.temp_c) / smp["minutes"]
                key, lo, hi, label = "exhaust_c_per_min", 0.05, 1.5, "exhaust cools the tent about %.2f °C per minute"
            new = learn_gain(self.learned.get(key), sample, lo, hi)
            if new is not None and new != self.learned.get(key):
                first = key not in self.learned
                self.learned[key] = new
                changed = True
                if first:
                    await self.store.add_event("info", "system", "Learned: " + label % new)
        self._pending_samples = keep
        if changed:
            await self.store.set_kv("learned", self.learned)

    async def _climate_check(self, ctx: ControlContext) -> None:
        """Once every ten minutes, look at the last hour: if the exhaust had to run most of the time and the tent
        is still at the top of the band, the light is making more heat than the tent can shed, and every pull of
        outside air is what keeps knocking the humidity down. Say so, once, with the fix."""
        now = utcnow()
        if self._climate_checked_at and (now - self._climate_checked_at).total_seconds() < CLIMATE_CHECK_S:
            return
        self._climate_checked_at = now
        if ctx.standby or ctx.sensor.stale or not ctx.lights_on:
            return
        duty = await self.exhaust_duty(1.0)
        readings = [r for r in await self.store.readings_since(1.0) if r.get("temp_c") is not None]
        if duty is None or len(readings) < 20:
            return
        temp = sum(r["temp_c"] for r in readings) / len(readings)
        rhs = [r["humidity"] for r in readings if r.get("humidity") is not None]
        rh = sum(rhs) / len(rhs) if rhs else None
        t = ctx.day_targets
        hot = duty >= CLIMATE_DUTY_LIMIT and temp >= t.temp_max_c - 0.5
        if hot and not self._climate_alert:
            msg = (f"Can't hold the climate: the exhaust ran {duty * 100:.0f}% of the last hour and the tent still averages "
                   f"{temp:.1f}°C (max {t.temp_max_c:g}°C)")
            if rh is not None and rh < t.humidity_min - 3:
                msg += f", and every pull of outside air drags humidity down (average {rh:.0f}%, target {t.humidity_min:g}–{t.humidity_max:g}%)"
            msg += (". The lights make more heat than the exhaust can remove without drying the tent: turn the dimmer down "
                    "or switch one light off. Hanging the light higher doesn't cool the tent.")
            await self.notifier.send("climate", msg, hours=6, title="Grow tent", everyone=True)
            await self.store.add_event("warn", "climate", msg)
            self._climate_alert = True
        elif self._climate_alert and (duty < CLIMATE_DUTY_LIMIT - 0.1 or temp < t.temp_max_c - 1.0):
            await self.store.resolve_alerts("climate", "Can't hold the climate")
            await self.store.add_event("info", "climate", f"Climate is holding again: exhaust {duty * 100:.0f}% of the last hour, {temp:.1f}°C.")
            self._climate_alert = False

    async def exhaust_duty(self, hours: float) -> Optional[float]:
        """Share of the last `hours` the exhaust was on, from the device log. None if it never switched."""
        rows = [r for r in await self.store.device_log_since(hours) if r["role"] == "exhaust_fan"]
        if not rows:
            # no switching in the window: it was either on or off the whole time
            last = self._last_known.get("exhaust_fan")
            return 1.0 if last == "on" else (0.0 if last == "off" else None)
        now = utcnow()
        start = now - timedelta(hours=hours)
        first = parse_iso(rows[0]["t"]) or start
        on_s = 0.0
        state = rows[0]["state"] != "on"          # before the first switch it was in the other state
        cursor = start
        for r in rows:
            at = parse_iso(r["t"]) or cursor
            if state:
                on_s += max(0.0, (at - cursor).total_seconds())
            state = r["state"] == "on"
            cursor = at
        if state:
            on_s += max(0.0, (now - cursor).total_seconds())
        return round(min(1.0, on_s / (hours * 3600.0)), 3)

    # ---- humidifier water: how many hours of misting since the last refill? ----
    async def _tank_load(self) -> dict:
        if self._tank is None:
            refill_at = await self.store.get_kv("humidifier_refill_at")
            if not refill_at:
                refill_at = iso(utcnow())
                await self.store.set_kv("humidifier_refill_at", refill_at)
            self._tank = {"run_s": float(await self.store.get_kv("humidifier_run_s", 0.0) or 0.0),
                          "refill_at": refill_at, "task_id": await self.store.get_kv("humidifier_refill_task")}
        return self._tank

    async def tank_status(self) -> Optional[dict]:
        tk = await self._tank_load()
        hours = float((await self.settings()).get("humidifier_tank_hours") or 4.0)
        return {"run_hours_since_refill": round(tk["run_s"] / 3600.0, 2), "tank_hours": hours,
                "refill_at": tk["refill_at"], "refill_task_id": tk["task_id"]}

    async def _tank_tracker(self, ctx: ControlContext) -> None:
        hum = ctx.devices.get("humidifier")
        if hum is None or not hum.entity_id:
            return
        tk = await self._tank_load()
        if tk["task_id"]:
            task = await self.store.get_task(tk["task_id"])
            if not task or task["status"] != "open":
                await self._tank_reset("Tank marked as refilled")
                return
        now = utcnow()
        if hum.state == "on" and self.last_cycle_at:
            tk["run_s"] += min(600.0, max(0.0, (now - self.last_cycle_at).total_seconds()))
            await self.store.set_kv("humidifier_run_s", tk["run_s"])
        hours = float((await self.settings()).get("humidifier_tank_hours") or 4.0)
        if tk["run_s"] >= 0.8 * hours * 3600.0 and not tk["task_id"]:
            await self._tank_alert(f"about {tk['run_s'] / 3600.0:.1f} h of misting since the last fill")

    async def _tank_alert(self, why: str) -> None:
        tk = await self._tank_load()
        if tk["task_id"]:
            return
        task = await self.store.add_task(
            "Refill the humidifier tank",
            f"Humidifier: {why}. Tick this off once it's filled and the counter starts again.",
            utcnow().date().isoformat(), "high", "system")
        tk["task_id"] = task["id"]
        await self.store.set_kv("humidifier_refill_task", task["id"])
        await self.store.add_event("warn", "device", f"Humidifier tank is probably low: {why}. Refill it.")
        await self.notifier.send("tank", f"Refill the humidifier tank: {why}.", hours=12, title="Grow tent", everyone=True)

    async def _tank_reset(self, why: str) -> None:
        tk = await self._tank_load()
        now = iso(utcnow())
        if tk["task_id"]:
            task = await self.store.get_task(tk["task_id"])
            if task and task["status"] == "open":
                await self.store.set_task_status(tk["task_id"], "done")
        tk.update(run_s=0.0, refill_at=now, task_id=None)
        await self.store.set_kv("humidifier_run_s", 0.0)
        await self.store.set_kv("humidifier_refill_at", now)
        await self.store.set_kv("humidifier_refill_task", None)
        await self.store.resolve_alerts("device", "Humidifier tank is probably low")
        await self.store.add_event("info", "device", f"{why}: misting counter reset.")

    async def _restore_switch_times(self) -> None:
        """After a restart, pick up when each device was last switched so pulses and rests carry on."""
        self._restored = True
        self.learned = await self.store.get_kv("learned", {}) or {}
        try:
            for role, t in (await self.store.last_device_switches()).items():
                when = parse_iso(t)
                if when and (utcnow() - when).total_seconds() < 24 * 3600:
                    self.last_switched.setdefault(role, when)
        except Exception:
            log.exception("could not restore switch times")

    # ---- power monitoring (smart plugs with energy metering, e.g. Tapo P110 / Kasa) ----
    def _numeric_sensor(self, entity_id: str) -> Optional[float]:
        st = self.states.get(entity_id)
        if not st or st["state"] in ("unavailable", "unknown", "", None):
            return None
        try:
            return float(st["state"])
        except (TypeError, ValueError):
            return None

    def _sibling_sensor(self, switch_entity: str, suffixes: tuple[str, ...]) -> Optional[str]:
        base = switch_entity.split(".", 1)[1]
        for suf in suffixes:
            eid = f"sensor.{base}{suf}"
            if eid in self.states:
                return eid
        return None

    def power_w(self, role: str, dmap: dict[str, str]) -> Optional[float]:
        eid = dmap.get(role)
        sensor = self._sibling_sensor(eid, POWER_SUFFIXES) if eid else None
        if not sensor:
            return None
        v = self._numeric_sensor(sensor)
        if v is None:
            return None
        unit = (self.states[sensor].get("attributes", {}).get("unit_of_measurement") or "W")
        return round(v * 1000, 1) if unit.lower() == "kw" else round(v, 1)

    def _kwh(self, sensor: str) -> Optional[float]:
        v = self._numeric_sensor(sensor)
        if v is None:
            return None
        unit = (self.states[sensor].get("attributes", {}).get("unit_of_measurement") or "kWh")
        return round(v / 1000, 3) if unit.lower() == "wh" else round(v, 3)

    def energy_kwh(self, role: str, dmap: dict[str, str], which: str) -> Optional[float]:
        eid = dmap.get(role)
        if not eid:
            return None
        sensor = self._sibling_sensor(eid, ENERGY_TODAY_SUFFIXES if which == "today" else ENERGY_MONTH_SUFFIXES)
        if sensor:
            return self._kwh(sensor)
        # Cumulative meter: today/month = now minus the baseline recorded at the start of the period.
        total_sensor = self._sibling_sensor(eid, ENERGY_TOTAL_SUFFIXES)
        if not total_sensor:
            return None
        now_kwh = self._kwh(total_sensor)
        base = self._energy_baselines.get((role, which))
        if now_kwh is None or base is None:
            return None
        return round(max(now_kwh - base, 0.0), 3)

    async def _update_energy_baselines(self, dmap: dict[str, str], now_local: datetime) -> None:
        """Remember each cumulative meter's reading at local midnight and on the 1st of the month (persisted)."""
        keys = {"today": now_local.strftime("%Y-%m-%d"), "month": now_local.strftime("%Y-%m")}
        stored = await self.store.get_kv("energy_baselines", {}) or {}
        changed = False
        for role in SWITCH_ROLES:
            eid = dmap.get(role)
            sensor = self._sibling_sensor(eid, ENERGY_TOTAL_SUFFIXES) if eid else None
            if not sensor:
                continue
            now_kwh = self._kwh(sensor)
            if now_kwh is None:
                continue
            for which, period in keys.items():
                k = f"{role}:{which}"
                rec = stored.get(k)
                if not rec or rec.get("period") != period or now_kwh < rec.get("kwh", 0):
                    stored[k] = {"period": period, "kwh": now_kwh}
                    changed = True
                self._energy_baselines[(role, which)] = stored[k]["kwh"]
        if changed:
            await self.store.set_kv("energy_baselines", stored)

    async def _power_watchdog(self, dmap: dict[str, str]) -> None:
        """A device that is switched ON but draws no power is broken, unplugged, or (humidifier) out of water."""
        now = utcnow()
        for role in SWITCH_ROLES:
            eid = dmap.get(role)
            st = self.states.get(eid) if eid else None
            if not st or st.get("state") != "on":
                self._on_since.pop(role, None)
                if self._power_warned.pop(role, None):
                    await self.store.resolve_alerts("device", f"{ROLE_BY_NAME[role].label} is switched on but drawing")
                continue
            self._on_since.setdefault(role, now)
            w = self.power_w(role, dmap)
            if w is None or (now - self._on_since[role]).total_seconds() < POWER_GRACE_S:
                continue
            if w < LOW_POWER_W.get(role, 3.0):
                last = self._power_warned.get(role)
                if last and (now - last).total_seconds() < 3600:
                    continue
                label = ROLE_BY_NAME[role].label
                hint = {"humidifier": "tank empty or unplugged?", "light": "driver/bulb dead or unplugged?"}.get(role, "unplugged or broken?")
                msg = f"{label} is switched on but drawing only {w:g} W — {hint}"
                await self.store.add_event("warn", "device", msg)
                await self.notifier.send(f"power:{role}", msg, hours=1, title="Grow tent", everyone=True)
                self._power_warned[role] = now
                if role == "humidifier":
                    await self._tank_alert("it has run dry")
            else:
                if self._power_warned.pop(role, None):
                    await self.store.resolve_alerts("device", f"{ROLE_BY_NAME[role].label} is switched on but drawing")
                    if role == "humidifier":
                        await self._tank_reset("Humidifier is drawing power again, so the tank was refilled")

    async def _report_safety(self, ctx: ControlContext, decisions: dict[str, Decision], results: dict[str, str]) -> None:
        s = ctx.sensor
        latch = ctx.safety_latch
        kind = None
        if latch == "hot":
            kind = "hot"
        elif latch == "cold":
            kind = "cold"
        elif not s.stale and s.humidity is not None and (s.humidity >= RH_CRITICAL or (self._safety_kind == "rh" and s.humidity >= RH_CRITICAL - 5)):
            kind = "rh"
        if kind and kind != self._safety_kind:
            now = f"{s.temp_c:.1f}°C" if s.temp_c is not None else "unknown temperature"
            head = {"hot": f"OVERHEATING: the tent reached {now} (cut-off {ctx.safety_temp_max_c:g}°C).",
                    "cold": f"TOO COLD: the tent is at {now} (limit {ctx.safety_temp_min_c:g}°C).",
                    "rh": f"HUMIDITY CRITICAL: {s.humidity:.0f}% (mould and bud-rot risk)."}[kind]
            words = {"switched": "done", "already": "done", "waiting": "pending",
                     "failed": "FAILED, do it by hand", "unavailable": "plug not responding, do it by hand"}
            parts = []
            for role in ("light", "exhaust_fan", "humidifier", "heater", "dehumidifier", "cooler"):
                dec = decisions.get(role)
                if dec is None or not dec.force or role not in results or results[role] == "unmapped":
                    continue
                parts.append(f"{ROLE_BY_NAME[role].label} {'on' if dec.desired else 'off'}: {words.get(results[role], results[role])}")
            msg = head + (" " + "; ".join(parts) + "." if parts else "")
            if kind == "hot":
                msg += " The lights stay off until the tent cools down."
            await self.notifier.send(f"safety:{kind}", msg, hours=1, everyone=True)
            await self.store.add_event("alert", "safety", msg)
            self._safety_kind = kind
        elif not kind and self._safety_kind:
            await self.store.add_event("info", "safety", "Safety condition cleared: the tent is back in a safe range.")
            for prefix in ("OVERHEATING", "TOO COLD", "HUMIDITY CRITICAL"):
                await self.store.resolve_alerts("safety", prefix)
            self._safety_kind = None

    async def run(self) -> None:
        await self._safe(self.store.add_event("info", "system", "Grow Brain started"), "event")
        n = 0
        while True:
            interval = 30
            try:
                self.last_attempt_at = utcnow()
                await self.cycle()
                if self.consecutive_failures >= LOOP_FAIL_ALERT:
                    await self._safe(self.store.resolve_alerts("system", "Tent automation is failing"), "resolve")
                    await self._safe(self.store.add_event("info", "system", "Tent automation is running normally again."), "event")
                self.consecutive_failures = 0
                self._loop_alerted = False
                n += 1
                if n % 2880 == 0:  # roughly daily at 30 s
                    await self._safe(self.store.prune(), "prune")
                settings = await self.settings()
                interval = int(settings.get("control_interval_s") or 30)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("control cycle failed")
                self.consecutive_failures += 1
                self.last_error = f"{type(e).__name__}: {e}"
                if self.consecutive_failures >= LOOP_FAIL_ALERT and not self._loop_alerted:
                    self._loop_alerted = True
                    msg = (f"Tent automation is failing ({self.last_error}). Devices stay as they are until it recovers: "
                           f"check the tent and tell Claude.")
                    await self._safe(self.notifier.send("loop", msg, hours=6, everyone=True), "notify")
                    await self._safe(self.store.add_event("alert", "system", msg), "event")
            await asyncio.sleep(max(10, min(300, interval)))

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())
        self._task.add_done_callback(self._loop_ended)

    def _loop_ended(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        log.error("control loop ended unexpectedly: %r; restarting it", exc)
        self.last_error = f"loop ended: {exc!r}"
        try:
            self.start()
        except RuntimeError:
            pass  # event loop shutting down

    def healthy(self) -> tuple[bool, str]:
        """For the Supervisor watchdog: is the control loop alive and cycling?"""
        now = utcnow()
        if self._task is not None and self._task.done():
            return False, "control loop is not running"
        if (now - self.started_at).total_seconds() < 300:
            return True, "starting"
        if self.last_attempt_at is None or (now - self.last_attempt_at).total_seconds() > 600:
            return False, "control loop is stuck"
        return True, "ok"

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    # ---- status for the API ----
    async def device_statuses(self) -> list[dict]:
        dmap = await self.store.get_device_map()
        overrides = await self.store.get_overrides()
        out = []
        for rd in ROLE_BY_NAME.values():
            eid = dmap.get(rd.role)
            st = self.states.get(eid) if eid else None
            if rd.kind == "sensor":
                state = st["state"] if st else "unknown"
                unit = (st or {}).get("attributes", {}).get("unit_of_measurement")
                if unit and state not in ("unknown", "unavailable"):
                    state = f"{state} {unit}"
                reason = "" if eid else "not mapped"
            else:
                state = st["state"] if st and st["state"] in ("on", "off") else "unknown"
                reason = self.last_reasons.get(rd.role, "" if eid else "not mapped")
            ov = overrides.get(rd.role)
            out.append({
                "role": rd.role, "label": rd.label, "kind": rd.kind, "entity_id": eid,
                "power_w": self.power_w(rd.role, dmap) if (eid and rd.kind == "switch") else None,
                "state": state, "mode": ov["mode"] if ov else "auto",
                "override_until": ov["until"] if ov else None,
                "reason": reason,
                "available": bool(st) and st["state"] not in ("unavailable", "unknown"),
            })
        return out


def _pdate(s: str | None):
    from datetime import date
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None
