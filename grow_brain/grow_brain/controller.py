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
HUM_HYST = 1.0       # humidifier stops as soon as RH is back inside the band
HUM_NEAR = 4.0       # within this many points of the minimum the humidifier runs in bursts
HUM_BURST_S = 180    # burst length; the tent hygrometer only reports every 2-3 minutes
HUM_REST_S = 240     # rest between bursts so the sensor can catch up before the next one
RH_EXHAUST_MARGIN = 3.0  # exhaust only dumps humidity this far above the max (mist settles on its own)
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


@dataclass
class Decision:
    role: str
    desired: Optional[bool]  # None = leave as is
    reason: str
    force: bool = False


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


# ---------------------------------------------------------------- light schedule

def light_window(now_local: datetime, on_time: str, hours: float) -> tuple[bool, datetime]:
    """Return (should_be_on, next_change_local)."""
    if hours <= 0:
        return False, now_local + timedelta(days=365)
    if hours >= 24:
        return True, now_local + timedelta(days=365)
    hh, mm = (int(x) for x in on_time.split(":"))
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

    def set_(role, desired, reason, force=False):
        if have(role):
            d[role] = Decision(role, desired, reason, force)

    # --- standby: nothing planted, everything off; manual overrides still respected ---
    if ctx.standby:
        for role in ctx.devices:
            set_(role, False, "tent in standby")
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
    if temp >= ctx.safety_temp_max_c:
        set_("light", False, f"SAFETY: {temp:.1f}°C ≥ {ctx.safety_temp_max_c:g}°C, lights off", force=True)
        set_("exhaust_fan", True, "SAFETY: overheating, exhaust on", force=True)
        set_("intake_fan", True, "SAFETY: overheating, intake on", force=True)
        set_("cooler", True, "SAFETY: overheating", force=True)
        set_("heater", False, "SAFETY: overheating", force=True)
        set_("humidifier", False, "SAFETY: overheating", force=True)
        set_("dehumidifier", False, "SAFETY: overheating (dehumidifier adds heat)", force=True)
        return _apply_overrides_and_pause(ctx, d)
    if temp <= ctx.safety_temp_min_c:
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
    too_dry = rh < t.humidity_min or (is_on("humidifier") and rh < t.humidity_min + HUM_HYST)

    # --- exhaust: reacts to heat and humidity, plus a baseline air-exchange duty while lights on ---
    exhaust_hot = temp > t.temp_max_c or (is_on("exhaust_fan") and temp > t.temp_max_c - TEMP_HYST)
    exhaust_humid = rh > t.humidity_max + RH_EXHAUST_MARGIN or (is_on("exhaust_fan") and rh > t.humidity_max)
    duty_on, duty_period = EXHAUST_DUTY_SEEDLING if ctx.stage == "seedling" else (EXHAUST_DUTY_ON_MIN, EXHAUST_DUTY_PERIOD_MIN)
    minute_of_period = (ctx.now_local.hour * 60 + ctx.now_local.minute) % duty_period
    duty = ctx.lights_on and minute_of_period < duty_on and ctx.stage not in ("curing", "done")
    ducted_note = "" if ctx.exhaust_ducted else " (not ducted outside yet: limited effect)"
    if rh >= RH_CRITICAL:
        set_("exhaust_fan", True, f"RH {rh:.1f}% critical, exhaust on" + ducted_note, force=True)
    elif exhaust_hot:
        set_("exhaust_fan", True, f"{temp:.1f}°C above max {t.temp_max_c:g}°C" + ducted_note)
    elif exhaust_humid:
        set_("exhaust_fan", True, f"RH {rh:.1f}% above max {t.humidity_max:g}%" + ducted_note)
    elif too_cold and not too_humid:
        set_("exhaust_fan", False, f"{temp:.1f}°C below min {t.temp_min_c:g}°C, keeping heat in")
    elif duty:
        set_("exhaust_fan", True, f"fresh-air exchange ({duty_on} min every {duty_period})")
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
    elif too_dry:
        # Don't fight the exhaust if it is on for heat; humidifying into an exhausting tent is wasteful
        # but still the right call when very dry, so only skip when exhaust is on for humidity.
        set_("humidifier", *_humidifier_burst(ctx, rh, t))
        set_("dehumidifier", False, "too dry")
    else:
        set_("humidifier", False, f"RH {rh:.1f}% within {t.humidity_min:g}–{t.humidity_max:g}%")
        set_("dehumidifier", False, f"RH {rh:.1f}% within {t.humidity_min:g}–{t.humidity_max:g}%")

    return _apply_overrides_and_pause(ctx, d)


def _humidifier_burst(ctx: ControlContext, rh: float, t: Targets) -> tuple[bool, str]:
    """Close to the minimum, run the humidifier in short bursts with rests in between. The hygrometer
    reports every few minutes, so running flat out until it *reads* in-band overshoots the band."""
    dev = ctx.devices.get("humidifier")
    if rh < t.humidity_min - HUM_NEAR or dev is None or dev.last_switched is None:
        return True, f"RH {rh:.1f}% below min {t.humidity_min:g}%"
    since = (ctx.now_local - dev.last_switched).total_seconds()
    if dev.state == "on" and since >= HUM_BURST_S:
        return False, f"RH {rh:.1f}%: burst done, letting the sensor catch up"
    if dev.state != "on" and since < HUM_REST_S:
        return False, f"RH {rh:.1f}%: resting between bursts"
    return True, f"RH {rh:.1f}% below min {t.humidity_min:g}% (burst)"


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

    # ---- config helpers (read from store each cycle so app changes apply immediately) ----
    async def settings(self) -> dict:
        s = await self.store.get_kv("settings", {}) or {}
        s.setdefault("timezone", self.boot_tz)
        s.setdefault("safety_temp_max_c", 35.0)
        s.setdefault("safety_temp_min_c", 12.0)
        s.setdefault("control_interval_s", 30)
        s.setdefault("min_switch_interval_s", 180)
        s.setdefault("auto_apply_advisor_targets", True)
        s.setdefault("units", "c")
        s.setdefault("brief_time", "08:00")
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
        base = stage_defaults(profile["stage"], day_in_stage, (override or {}).get("light_on_time", "06:00"))
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
            )
        light_state = devices["light"].state if devices.get("light") else None
        lights_on = light_state == "on" if light_state is not None else scheduled_on
        targets = day_targets if lights_on else day_targets.for_night()
        return ControlContext(
            now_local=now_local, stage=profile["stage"], targets=targets, day_targets=day_targets,
            light_scheduled_on=scheduled_on, lights_on=lights_on, sensor=self.sensor,
            safety_temp_max_c=float(settings["safety_temp_max_c"]), safety_temp_min_c=float(settings["safety_temp_min_c"]),
            exhaust_ducted=bool(profile.get("exhaust_ducted")), paused=bool(await self.paused_until()),
            devices=devices, standby=await self.standby(),
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

    async def cycle(self) -> None:
        try:
            states = await self.ha.get_states()
        except Exception as e:
            self.ha_ok = False
            if not self._ha_fail_reported:
                await self.store.add_event("alert", "system", f"Cannot reach Home Assistant: {e}")
                self._ha_fail_reported = True
            return
        if self._ha_fail_reported:
            await self.store.add_event("info", "system", "Home Assistant connection restored")
            self._ha_fail_reported = False
        if not self.ha_ok:
            # first good cycle since startup (or since an outage): any older "cannot reach" alert is over
            await self.store.resolve_alerts("system", "Cannot reach Home Assistant")
        self.ha_ok = True
        self.states = {s["entity_id"]: s for s in states}

        dmap = await self.store.get_device_map()
        _s = await self.settings()
        self._offsets = (float(_s.get("temp_offset_c") or 0.0), float(_s.get("humidity_offset") or 0.0))
        self.sensor = self._read_sensors(dmap)
        ctx = await self.build_context()
        await self._power_watchdog(dmap)
        await self._update_energy_baselines(dmap, ctx.now_local)

        if self.sensor.stale and not self._stale_reported and dmap.get("temperature_sensor"):
            await self.store.add_event("warn", "safety", "Tent sensor is stale or unavailable. Running in safe mode (exhaust on, climate devices off).")
            await self.notifier.send("stale", "Tent sensor is not reporting. Automation is in safe mode.", hours=6)
            self._stale_reported = True
        elif not self.sensor.stale and self._stale_reported:
            await self.store.add_event("info", "safety", "Tent sensor is reporting again.")
            await self.store.resolve_alerts("safety", "Tent sensor is stale")
            self._stale_reported = False

        if not self.sensor.stale:
            await self.store.add_reading(self.sensor.temp_c, self.sensor.humidity, self.sensor.vpd_kpa,
                                         self.sensor.co2, ctx.lights_on)

        self._last_lights_on = ctx.lights_on
        decisions = decide(ctx)
        await self._report_safety(ctx, decisions)
        settings = await self.settings()
        min_iv = int(settings["min_switch_interval_s"])
        now = utcnow()
        for role, dec in decisions.items():
            dev = ctx.devices[role]
            self.last_reasons[role] = dec.reason
            if dec.desired is None or not dev.entity_id or not dev.available:
                continue
            if dev.state == ("on" if dec.desired else "off"):
                continue
            iv = max(min_iv, 300) if role in ("dehumidifier", "cooler") else min_iv
            last = self.last_switched.get(role)
            if last and not dec.force and (now - last).total_seconds() < iv:
                self.last_reasons[role] = dec.reason + " (waiting for minimum switch interval)"
                continue
            ok = await self.ha.turn(dev.entity_id, dec.desired)
            if ok:
                self.last_switched[role] = now
                await self.store.log_device(role, "on" if dec.desired else "off", dec.reason)
                await self.store.add_event("info", "device",
                                           f"{ROLE_BY_NAME[role].label} → {'ON' if dec.desired else 'OFF'}: {dec.reason}")
                # optimistic local state so the next cycle's hysteresis sees it
                self.states.setdefault(dev.entity_id, {})["state"] = "on" if dec.desired else "off"
        self.last_cycle_at = now

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
            else:
                if self._power_warned.pop(role, None):
                    await self.store.resolve_alerts("device", f"{ROLE_BY_NAME[role].label} is switched on but drawing")

    async def _report_safety(self, ctx: ControlContext, decisions: dict[str, Decision]) -> None:
        active = None
        if ctx.standby:
            return
        t = ctx.sensor.temp_c
        if t is not None and not ctx.sensor.stale:
            if t >= ctx.safety_temp_max_c:
                active = f"OVERHEATING: tent is {t:.1f}°C. Lights off, exhaust on."
            elif t <= ctx.safety_temp_min_c:
                active = f"TOO COLD: tent is {t:.1f}°C. Heater on."
            elif ctx.sensor.humidity is not None and ctx.sensor.humidity >= RH_CRITICAL:
                active = f"HUMIDITY CRITICAL: {ctx.sensor.humidity:.0f}% RH. Bud rot risk. Exhaust and dehumidifier on."
        if active and active != self._safety_reported:
            await self.store.add_event("alert", "safety", active)
            await self.notifier.send("safety", active, hours=1)
            self._safety_reported = active
        elif not active and self._safety_reported:
            await self.store.add_event("info", "safety", "Safety condition cleared.")
            for prefix in ("OVERHEATING", "TOO COLD", "HUMIDITY CRITICAL"):
                await self.store.resolve_alerts("safety", prefix)
            self._safety_reported = None

    async def run(self) -> None:
        await self.store.add_event("info", "system", "Grow Brain started")
        n = 0
        while True:
            try:
                await self.cycle()
            except Exception:
                log.exception("control cycle failed")
            n += 1
            if n % 2880 == 0:  # roughly daily at 30 s
                try:
                    await self.store.prune()
                except Exception:
                    log.exception("prune failed")
            settings = await self.settings()
            await asyncio.sleep(max(10, int(settings.get("control_interval_s", 30))))

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())

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
