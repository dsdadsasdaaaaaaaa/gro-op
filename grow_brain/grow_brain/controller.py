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

TEMP_HYST = 1.0      # °C
RH_HYST = 4.0        # % RH
RH_CRITICAL = 85.0   # bud-rot territory; always dehumidify/exhaust above this
STALE_AFTER_S = 30 * 60
EXHAUST_DUTY_ON_MIN = 5
EXHAUST_DUTY_PERIOD_MIN = 20


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
    too_dry = rh < t.humidity_min or (is_on("humidifier") and rh < t.humidity_min + RH_HYST)

    # --- exhaust: reacts to heat and humidity, plus a baseline air-exchange duty while lights on ---
    exhaust_hot = temp > t.temp_max_c or (is_on("exhaust_fan") and temp > t.temp_max_c - TEMP_HYST)
    exhaust_humid = rh > t.humidity_max or (is_on("exhaust_fan") and rh > t.humidity_max - RH_HYST)
    minute_of_period = (ctx.now_local.hour * 60 + ctx.now_local.minute) % EXHAUST_DUTY_PERIOD_MIN
    duty = ctx.lights_on and minute_of_period < EXHAUST_DUTY_ON_MIN and ctx.stage not in ("curing", "done")
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
        set_("exhaust_fan", True, f"fresh-air exchange ({EXHAUST_DUTY_ON_MIN} min every {EXHAUST_DUTY_PERIOD_MIN})")
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
        set_("humidifier", True, f"RH {rh:.1f}% below min {t.humidity_min:g}%")
        set_("dehumidifier", False, "too dry")
    else:
        set_("humidifier", False, f"RH {rh:.1f}% within {t.humidity_min:g}–{t.humidity_max:g}%")
        set_("dehumidifier", False, f"RH {rh:.1f}% within {t.humidity_min:g}–{t.humidity_max:g}%")

    return _apply_overrides_and_pause(ctx, d)


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
        self.ha_ok = True
        self.states = {s["entity_id"]: s for s in states}

        dmap = await self.store.get_device_map()
        self.sensor = self._read_sensors(dmap)
        ctx = await self.build_context()

        if self.sensor.stale and not self._stale_reported and dmap.get("temperature_sensor"):
            await self.store.add_event("warn", "safety", "Tent sensor is stale or unavailable. Running in safe mode (exhaust on, climate devices off).")
            await self.notifier.send("stale", "Tent sensor is not reporting. Automation is in safe mode.", hours=6)
            self._stale_reported = True
        elif not self.sensor.stale and self._stale_reported:
            await self.store.add_event("info", "safety", "Tent sensor is reporting again.")
            self._stale_reported = False

        if not self.sensor.stale:
            await self.store.add_reading(self.sensor.temp_c, self.sensor.humidity, self.sensor.vpd_kpa,
                                         self.sensor.co2, ctx.lights_on)

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
