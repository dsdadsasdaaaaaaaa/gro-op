"""Device roles and Home Assistant entity auto-mapping."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleDef:
    role: str
    label: str
    kind: str  # "switch" | "sensor"
    required: bool
    description: str
    keywords: tuple[str, ...]
    negative: tuple[str, ...] = ()


ROLES: list[RoleDef] = [
    RoleDef("light", "Grow light", "switch", True, "The main grow light. Runs on the stage's light schedule.",
            ("grow light", "light", "lamp", "led", "hlg", "spider", "mars", "viparspectra")),
    RoleDef("exhaust_fan", "Exhaust fan", "switch", True, "Pulls hot/humid air out of the tent. Used to lower temperature and humidity.",
            ("exhaust", "extractor", "outtake", "out take", "vent fan", "inline")),
    RoleDef("intake_fan", "Intake fan", "switch", False, "Brings fresh air in. Runs together with the exhaust fan.",
            ("intake", "in take", "inlet")),
    RoleDef("circulation_fan", "Circulation fan", "switch", False, "Oscillating/clip fan inside the tent. Runs constantly.",
            ("circulation", "clip fan", "oscillating", "osc", "circ", "tent fan", "fan 1", "fan1", "fan")),
    RoleDef("circulation_fan_2", "Circulation fan 2", "switch", False, "Second circulation fan.",
            ("circulation 2", "clip fan 2", "fan 2", "fan2", "circ 2")),
    RoleDef("humidifier", "Humidifier", "switch", False, "Raises humidity when it is below target.",
            ("humidifier", "humid", "mist", "fogger"), negative=("dehumid",)),
    RoleDef("dehumidifier", "Dehumidifier", "switch", False, "Lowers humidity when it is above target.",
            ("dehumidifier", "dehumid", "dry")),
    RoleDef("heater", "Heater", "switch", False, "Raises temperature when it is below target.",
            ("heater", "heat mat", "heating mat", "heating pad"), negative=("overheat", "preheat", "active", "mode")),
    RoleDef("cooler", "AC / cooler", "switch", False, "Lowers temperature when it is above target.",
            ("ac", "a/c", "air con", "cooler", "cooling", "chiller")),
    RoleDef("temperature_sensor", "Temperature sensor", "sensor", True, "Air temperature inside the tent.",
            ("temperature", "temp")),
    RoleDef("humidity_sensor", "Humidity sensor", "sensor", True, "Relative humidity inside the tent.",
            ("humidity", "humid", "rh")),
    RoleDef("vpd_sensor", "VPD sensor", "sensor", False, "Optional. If not mapped, VPD is computed from temperature and humidity.",
            ("vpd", "vapor", "vapour")),
    RoleDef("co2_sensor", "CO2 sensor", "sensor", False, "Optional CO2 sensor.",
            ("co2", "carbon")),
]

ROLE_BY_NAME = {r.role: r for r in ROLES}
SWITCH_ROLES = [r.role for r in ROLES if r.kind == "switch"]
SENSOR_ROLES = [r.role for r in ROLES if r.kind == "sensor"]

SWITCH_DOMAINS = {"switch", "light", "fan", "input_boolean", "humidifier", "climate"}
SENSOR_DOMAINS = {"sensor"}

# Words that suggest an entity is a power/energy sub-sensor of a smart plug, not a climate sensor.
_PLUG_SENSOR_WORDS = ("power", "energy", "current", "voltage", "kwh", "watt", " w ", "signal", "rssi",
                      "linkquality", "battery", "uptime", "wifi", "ip", "mac")


# Sub-feature entities that smart plugs, cameras etc. expose next to the real switch.
_SUB_FEATURE_WORDS = (" led", "auto off", "auto-off", "auto update", "auto-update", "status light", "night vision",
                      "motion", "notifications", "stream", "recording", "detection", "flip ", "wiper", "autofocus",
                      "announcements", "communications", "do not disturb", "dimmed", "adaptive", "circadian",
                      "consumption", "auto off at")


def _norm(s: str) -> str:
    s = s.lower().replace("_", " ").replace("-", " ").replace(".", " ")
    return re.sub(r"\s+", " ", s).strip()


def suggest_role(entity_id: str, friendly_name: str | None, device_class: str | None, unit: str | None) -> str | None:
    """Best-effort role guess for one HA entity. Returns a role name or None."""
    domain = entity_id.split(".", 1)[0]
    text = f" {_norm(friendly_name or '')} {_norm(entity_id.split('.', 1)[1])} "

    if domain in SENSOR_DOMAINS:
        if any(w in text for w in _PLUG_SENSOR_WORDS) or any(w in text for w in _SUB_FEATURE_WORDS):
            return None
        if device_class == "temperature" and unit in ("°C", "°F"):
            return "temperature_sensor"
        if device_class == "humidity" and unit == "%":
            return "humidity_sensor"
        if device_class == "carbon_dioxide" or (unit == "ppm" and " co2 " in text):
            return "co2_sensor"
        if unit == "kPa" or (" vpd " in text and unit):
            return "vpd_sensor"
        if unit in ("°C", "°F") and re.search(r"\b(temp|temperature)\b", text) and "target" not in text and "outside" not in text:
            return "temperature_sensor"
        if unit == "%" and re.search(r"\b(humidity|rh)\b", text):
            return "humidity_sensor"
        return None

    if any(w in text for w in _SUB_FEATURE_WORDS):
        return None
    if domain == "input_boolean":
        return None  # helpers/flags, never real devices

    if domain not in SWITCH_DOMAINS:
        return None

    # Switch-like entity: score by keyword, honouring negatives and specificity (longer keywords first).
    best: tuple[int, str] | None = None
    for r in ROLES:
        if r.kind != "switch":
            continue
        if any(n in text for n in r.negative):
            continue
        for kw in r.keywords:
            if f" {kw} " in text or (len(kw) > 3 and kw in text):
                score = len(kw)
                if best is None or score > best[0]:
                    best = (score, r.role)
                break
    if best is None and domain == "light":
        return "light"
    if best is None and domain == "humidifier":
        return "humidifier"
    return best[1] if best else None


def automap(entities: list[dict]) -> dict[str, str]:
    """Given HA entity summaries (from HAClient.list_candidates), return {role: entity_id}.

    Only fills roles that are unambiguous (one good candidate). If several entities match one
    role, the one with the more specific (longer) keyword match wins; ties go to the first.
    """
    candidates: dict[str, list[tuple[int, str]]] = {}
    for e in entities:
        role = e.get("suggested_role")
        if not role:
            continue
        domain = (e.get("entity_id") or "").split(".", 1)[0]
        if domain in ("climate", "input_boolean", "automation", "script", "cover", "lock", "alarm_control_panel"):
            continue   # never let a guess switch the house's thermostat, helpers or doors
        name = _norm(e.get("name") or "")
        spec = max((len(k) for k in ROLE_BY_NAME[role].keywords if k in name), default=0)
        if any(w in name for w in ("grow", "tent", "hygrometer")):
            spec += 100  # an entity the user named after the grow beats any room device
        candidates.setdefault(role, []).append((spec, e["entity_id"]))
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for role, lst in candidates.items():
        lst.sort(key=lambda x: -x[0])
        for _, eid in lst:
            if eid not in used:
                mapping[role] = eid
                used.add(eid)
                break
    # A "fan" that was captured as circulation_fan while an explicit exhaust exists is fine; but if
    # there's no exhaust and only generic fans, leave exhaust unmapped so the user picks it.
    return mapping
