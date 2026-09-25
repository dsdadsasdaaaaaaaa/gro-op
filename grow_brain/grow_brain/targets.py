"""Environmental targets per grow stage and VPD math.

Defaults are tuned for Liberty Haze (Barney's Farm), a sativa-leaning photoperiod hybrid,
grown in a small tent under LED. The advisor (Claude) may nudge these within safe bounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, replace
from datetime import date

STAGES = ["seedling", "veg", "flower", "flush", "drying", "curing", "done"]

# Leaf temperature is usually a little below air temperature under LEDs.
LEAF_TEMP_OFFSET_C = 1.0


def svp_kpa(temp_c: float) -> float:
    """Saturation vapour pressure (kPa), Tetens formula."""
    return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))


def vpd_kpa(air_temp_c: float, rh_percent: float, leaf_offset_c: float = LEAF_TEMP_OFFSET_C) -> float:
    """Leaf VPD in kPa given air temp, RH and an assumed leaf-air temperature offset."""
    leaf_t = air_temp_c - leaf_offset_c
    vpd = svp_kpa(leaf_t) - svp_kpa(air_temp_c) * (rh_percent / 100.0)
    return round(max(vpd, 0.0), 2)


def c_to_f(c: float) -> float:
    return round(c * 9 / 5 + 32, 1)


def f_to_c(f: float) -> float:
    return round((f - 32) * 5 / 9, 1)


@dataclass
class Targets:
    temp_min_c: float
    temp_max_c: float
    humidity_min: float
    humidity_max: float
    vpd_min: float
    vpd_max: float
    light_on_time: str  # "HH:MM" local
    light_hours: float
    night_temp_drop_c: float = 3.0  # how much lower the temp band sits when lights are off
    source: str = "stage_default"  # stage_default | advisor | manual
    note: str = ""

    def to_api(self) -> dict:
        d = asdict(self)
        d["temp_min_f"] = c_to_f(self.temp_min_c)
        d["temp_max_f"] = c_to_f(self.temp_max_c)
        return d

    def for_night(self) -> "Targets":
        """Targets to enforce while lights are off (cooler band, same humidity band)."""
        drop = self.night_temp_drop_c
        if not drop:
            return replace(self, note=(self.note + " " if self.note else "") + "(night band)")
        return replace(
            self,
            # a basement tent with no heater sits near 18-20 °C at night, which plants handle fine
            temp_min_c=round(min(self.temp_min_c - drop, 18.0), 1),
            temp_max_c=round(self.temp_max_c - drop + 1.0, 1),
            note=(self.note + " " if self.note else "") + "(night band)",
        )


# Hard bounds the advisor can never push targets outside of.
BOUNDS = {
    "temp_min_c": (15.0, 30.0),
    "temp_max_c": (18.0, 32.0),
    "humidity_min": (25.0, 80.0),
    "humidity_max": (30.0, 85.0),
    "vpd_min": (0.3, 1.8),
    "vpd_max": (0.5, 2.0),
    "light_hours": (0.0, 24.0),
}

# VPD is shown to the growers but the controller doesn't act on it, so the advisor can't "fix" it by moving a number.
ADJUSTABLE_BY_ADVISOR = {"temp_min_c", "temp_max_c", "humidity_min", "humidity_max"}


_BLEND_FIELDS = ("temp_min_c", "temp_max_c", "humidity_min", "humidity_max", "vpd_min", "vpd_max", "night_temp_drop_c")


def _blend(a: Targets, b: Targets, day: int, start: int, span: int = 3) -> Targets:
    """a until `start`, then over `span` days toward b: plants handle a slow change better than a jump.
    Light hours and the note switch to b's straight away (the photoperiod change has to be exact)."""
    if day < start:
        return a
    if day >= start + span:
        return b
    f = (day - start + 1) / (span + 1)
    t = replace(b)
    for k in _BLEND_FIELDS:
        setattr(t, k, round(getattr(a, k) + (getattr(b, k) - getattr(a, k)) * f, 1 if "vpd" not in k else 2))
    t.note = b.note + " (easing in over a few days)"
    return t


def stage_defaults(stage: str, day_in_stage: int = 0, light_on_time: str = "06:00") -> Targets:
    """Textbook targets for each phase, led by VPD (Liberty Haze, a sativa-leaning hybrid, in soil under LED).
    Within veg and flower the numbers move with the week, easing over 3 days instead of jumping."""
    lo = light_on_time
    seedling = Targets(22.0, 26.0, 65.0, 75.0, 0.4, 0.8, lo, 18, night_temp_drop_c=2.0,
                       note="Seedling: warm and humid (VPD 0.4–0.8), gentle light, 18/6")
    early_veg = Targets(22.0, 27.0, 60.0, 70.0, 0.8, 1.0, lo, 18, night_temp_drop_c=3.0,
                        note="Early veg: humid while the roots settle into the big pot (VPD 0.8–1.0), 18/6")
    late_veg = Targets(23.0, 28.0, 55.0, 65.0, 0.9, 1.2, lo, 18, night_temp_drop_c=3.0,
                       note="Late veg: warm, a little drier for fast growth (VPD 0.9–1.2), 18/6")
    stretch = Targets(22.0, 27.0, 50.0, 60.0, 1.0, 1.3, lo, 12, night_temp_drop_c=3.0,
                      note="Flower weeks 1–3 (stretch): 12/12, humidity coming down (VPD 1.0–1.3)")
    bulk = Targets(21.0, 26.0, 45.0, 52.0, 1.2, 1.4, lo, 12, night_temp_drop_c=4.0,
                   note="Flower weeks 4–7 (bulking): RH ≤52 % against bud rot (VPD 1.2–1.4)")
    ripen = Targets(20.0, 25.0, 40.0, 48.0, 1.3, 1.6, lo, 12, night_temp_drop_c=5.0,
                    note="Flower week 8+ (ripening): cooler nights keep the terpenes, RH low (VPD 1.3–1.6)")
    if stage == "seedling":
        return seedling
    if stage == "veg":
        return _blend(early_veg, late_veg, day_in_stage, 14)
    if stage == "flower":
        if day_in_stage < 21:
            return _blend(late_veg, stretch, day_in_stage, 0)   # 12/12 from day 0; the climate eases in from late veg
        if day_in_stage < 49:
            return _blend(stretch, bulk, day_in_stage, 21)
        return _blend(bulk, ripen, day_in_stage, 49)
    if stage == "flush":
        return Targets(20.0, 24.0, 40.0, 45.0, 1.3, 1.6, lo, 12, night_temp_drop_c=5.0,
                       note="Flush: plain water only, RH low, cooler nights")
    if stage == "drying":
        return Targets(16.0, 20.0, 55.0, 62.0, 0.6, 1.0, lo, 0, night_temp_drop_c=0.0,
                       note="Drying: lights OFF, the 60/60 rule (≈16–20 °C, 55–62 % RH), gentle air that doesn't hit the buds")
    if stage == "curing":
        return Targets(18.0, 22.0, 58.0, 65.0, 0.6, 1.0, lo, 0, night_temp_drop_c=0.0,
                       note="Curing: jars at ~62 % RH; tent control mostly idle")
    return Targets(18.0, 28.0, 40.0, 60.0, 0.6, 1.5, lo, 0, night_temp_drop_c=0.0, note="No active grow")


# Light power at the light plug that each phase wants (W). All three lights at full ≈ 440 W; the big one
# alone at ~75 % ≈ 175 W. There's no dimmer control, so the advisor tells the growers what to change.
def light_power_target(stage: str, day_in_stage: int = 0) -> tuple[float, float, str] | None:
    if stage == "seedling":
        return 150.0, 190.0, "only the big light, dimmer about 75 %"
    if stage == "veg":
        if day_in_stage < 14:
            return 250.0, 350.0, "all three lights, big one about halfway, turned up week by week"
        return 350.0, 441.0, "all three lights, big one turned up toward full"
    if stage in ("flower", "flush"):
        return 400.0, 441.0, "everything at full"
    return None


def apply_overrides(base: Targets, overrides: dict | None, source: str) -> Targets:
    if not overrides:
        return base
    t = replace(base)
    for k, v in overrides.items():
        if k in BOUNDS and v is not None:
            lo, hi = BOUNDS[k]
            setattr(t, k, float(min(max(float(v), lo), hi)))
        elif k == "light_on_time" and isinstance(v, str) and len(v) == 5 and v[2] == ":":
            t.light_on_time = v
    if t.temp_max_c <= t.temp_min_c:
        t.temp_max_c = t.temp_min_c + 2.0
    if t.humidity_max <= t.humidity_min:
        t.humidity_max = t.humidity_min + 5.0
    if t.vpd_max <= t.vpd_min:
        t.vpd_max = t.vpd_min + 0.3
    t.source = source
    return t


def days_between(a: date | None, b: date) -> int:
    if a is None:
        return 0
    return max((b - a).days, 0)
