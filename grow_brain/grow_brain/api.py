"""HTTP API for the iOS app. See docs/API.md for the contract."""

from __future__ import annotations

import io
import logging
import mimetypes
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from . import __version__
from .advisor import Advisor, AdvisorError
from .controller import Controller, light_window
from .devices import ROLE_BY_NAME, ROLES, SWITCH_ROLES, automap
from .models import (CameraAnalyse, CameraSelect, ChatRequest, DeviceMapUpdate, GrowProfile, GrowProfileUpdate, LogCreate,
                     OverrideRequest, PauseRequest, PlantCreate, PlantUpdate, SettingsModel, SettingsUpdate, StageChange,
                     TargetsUpdate, TaskCreate)
from .store import Store, iso, utcnow
from .plan import build_plan
from .targets import STAGES, stage_defaults

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ wiring

def deps(request: Request):
    return request.app.state


async def require_key(request: Request):
    st = request.app.state
    key = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if key != st.boot.api_key:
        raise HTTPException(401, "Invalid or missing X-API-Key")


auth = [Depends(require_key)]


@router.get("/health")
async def health(request: Request):
    st = request.app.state
    return {"ok": True, "version": __version__, "ha_connected": st.controller.ha_ok, "advisor_enabled": st.advisor.enabled}


# ------------------------------------------------------------------ plants

def _plant_api(p: dict, today: date) -> dict:
    out = {k: p[k] for k in ("id", "name", "owner", "strain", "breeder", "seed_type", "medium", "pot_size_l", "start_date",
                             "notes", "notify_service", "created_at")}
    try:
        out["day_total"] = max((today - date.fromisoformat(p["start_date"])).days, 0) if p.get("start_date") else 0
    except ValueError:
        out["day_total"] = 0
    return out


async def _plants_api(request: Request) -> list[dict]:
    st = request.app.state
    today = datetime.now(st.controller.tz(await st.controller.settings())).date()
    return [_plant_api(p, today) for p in await st.store.plants()]


@router.get("/plants", dependencies=auth)
async def list_plants(request: Request):
    return {"plants": await _plants_api(request)}


@router.post("/plants", dependencies=auth)
async def create_plant(body: PlantCreate, request: Request):
    st = request.app.state
    p = await st.store.add_plant(**body.model_dump())
    await st.store.add_event("info", "system", f"Plant added: {p['name']} ({p['owner'] or 'no owner'})")
    return _plant_api(p, datetime.now(st.controller.tz(await st.controller.settings())).date())


@router.put("/plants/{pid}", dependencies=auth)
async def update_plant(pid: int, body: PlantUpdate, request: Request):
    st = request.app.state
    if not await st.store.get_plant(pid):
        raise HTTPException(404, "No such plant")
    p = await st.store.update_plant(pid, **body.model_dump(exclude_unset=True))
    return _plant_api(p, datetime.now(st.controller.tz(await st.controller.settings())).date())


@router.delete("/plants/{pid}", dependencies=auth)
async def delete_plant(pid: int, request: Request):
    st = request.app.state
    p = await st.store.get_plant(pid)
    if not p:
        raise HTTPException(404, "No such plant")
    await st.store.archive_plant(pid)
    await st.store.add_event("info", "system", f"Plant removed: {p['name']}")
    return {"ok": True}


# ------------------------------------------------------------------ status / history

async def _assessment(controller: Controller, targets, sensor, paused, units: str = "c", standby: bool = False) -> dict:
    from .targets import c_to_f
    details, level = [], "good"
    if standby:
        det = []
        if sensor.temp_c is not None and not sensor.stale:
            det.append(f"Tent air {c_to_f(sensor.temp_c):g}°F, {sensor.humidity:g}% RH" if units == "f" else f"Tent air {sensor.temp_c:g}°C, {sensor.humidity:g}% RH")
        return {"level": "standby", "headline": "Tent is off", "details": det + ["Start it when the seedling goes in"]}
    if not controller.ha_ok:
        return {"level": "alert", "headline": "Can't reach Home Assistant", "details": [controller.ha.last_error or "connection failed"]}
    dmap = await controller.store.get_device_map()
    if not dmap.get("temperature_sensor") or not dmap.get("humidity_sensor"):
        return {"level": "warn", "headline": "Set up your devices", "details": ["Map the tent sensor and switches in Settings → Devices"]}
    if sensor.stale:
        return {"level": "alert", "headline": "Sensor not reporting", "details": ["Automation is in safe mode until the sensor comes back"]}

    def check(val, lo, hi, name, unit, warn_margin, alert_margin, fmt=lambda x: f"{x:g}"):
        nonlocal level
        if val is None:
            return
        off = lo - val if val < lo else val - hi if val > hi else 0.0
        if off <= warn_margin * 0.4:  # small dead-band: the controller is already correcting
            details.append(f"{name} {fmt(val)}{unit} in range {fmt(lo)}–{fmt(hi)}{unit}")
            return
        sev = "alert" if off >= alert_margin else "warn"
        level = "alert" if sev == "alert" or level == "alert" else "warn"
        details.append(f"{name} {fmt(val)}{unit} {'below' if val < lo else 'above'} target {fmt(lo)}–{fmt(hi)}{unit}")

    if units == "f":
        check(sensor.temp_c, targets.temp_min_c, targets.temp_max_c, "Temp", "°F", 1.5, 4.0, fmt=lambda c: f"{c_to_f(c):g}")
    else:
        check(sensor.temp_c, targets.temp_min_c, targets.temp_max_c, "Temp", "°C", 1.5, 4.0)
    check(sensor.humidity, targets.humidity_min, targets.humidity_max, "Humidity", "%", 5.0, 12.0)
    check(sensor.vpd_kpa, targets.vpd_min, targets.vpd_max, "VPD", " kPa", 0.2, 0.5)
    headline = {"good": "Everything on target", "warn": "Slightly off target, adjusting", "alert": "Out of range"}[level]
    if paused:
        headline += " (automation paused)"
    return {"level": level, "headline": headline, "details": details}


@router.get("/status", dependencies=auth)
async def status(request: Request):
    st = request.app.state
    c: Controller = st.controller
    settings = await c.settings()
    profile = await c.profile()
    tz = c.tz(settings)
    now_local = datetime.now(tz)
    day_targets, day_in_stage, day_total = await c.effective_targets(profile, settings)
    scheduled_on, next_change = light_window(now_local, day_targets.light_on_time, day_targets.light_hours)
    devices = await c.device_statuses()
    light_dev = next((d for d in devices if d["role"] == "light"), None)
    light_is_on = light_dev["state"] == "on" if light_dev and light_dev["state"] in ("on", "off") else scheduled_on
    active_targets = day_targets if light_is_on else day_targets.for_night()
    paused = await c.paused_until()
    standby = await c.standby()
    harvest = None
    if profile.get("flower_start_date"):
        try:
            harvest = (date.fromisoformat(profile["flower_start_date"]) + timedelta(days=int(profile.get("expected_flower_days") or 65))).isoformat()
        except ValueError:
            harvest = None
    alerts = [{"id": e["id"], "level": e["level"], "message": e["message"], "at": e["at"]}
              for e in await st.store.events(5, min_level="warn", hours=6)]
    plants = await _plants_api(request)
    if plants:
        day_total = plants[0]["day_total"]
    return {
        "plants": plants,
        "camera": await st.camera.info(),
        "time": iso(utcnow()),
        "ha_connected": c.ha_ok,
        "sensor": c.sensor.to_api(),
        "grow": {**profile, "day_in_stage": day_in_stage, "day_total": day_total, "expected_harvest_date": harvest},
        "targets": active_targets.to_api(),
        "light": {"is_on": light_is_on, "next_change_at": iso(next_change), "schedule": _sched(day_targets.light_hours)},
        "devices": devices,
        "assessment": await _assessment(c, active_targets, c.sensor, paused, settings.get("units", "c"), standby),
        "standby": standby,
        "open_tasks": len(await st.store.tasks("open")),
        "open_photo_requests": len(await st.store.photo_requests("open")),
        "unread_brief": await st.store.unread_brief(),
        "alerts": alerts,
        "control_paused_until": paused,
    }


@router.get("/plan", dependencies=auth)
async def plan(request: Request, plant_id: Optional[int] = None):
    st = request.app.state
    c: Controller = st.controller
    settings = await c.settings()
    profile = await c.profile()
    _, day_in_stage, day_total = await c.effective_targets(profile, settings)
    today = datetime.now(c.tz(settings)).date()
    plants = await st.store.plants()
    plant = next((p for p in plants if p["id"] == plant_id), None) or (plants[0] if plants else None)
    if plant and plant.get("start_date"):
        profile = {**profile, "start_date": plant["start_date"]}
        try:
            day_total = max((today - date.fromisoformat(plant["start_date"])).days, 0)
        except ValueError:
            pass
    entries = await st.store.log_entries(300)
    planted = any((e["kind"] == "transplant" or (e.get("context") or "").lower() in ("planted", "planting"))
                  and (plant is None or e.get("plant_id") in (None, plant["id"]))
                  for e in entries if e["created_at"][:10] >= (profile.get("stage_started") or "0000"))
    out = build_plan(profile, today, day_in_stage, day_total, planted)
    out["plant_id"] = plant["id"] if plant else None
    return out


def _sched(hours: float) -> str:
    if hours <= 0:
        return "off"
    if hours >= 24:
        return "24/0"
    return f"{hours:g}/{24 - hours:g}"


@router.get("/history", dependencies=auth)
async def history(request: Request, hours: float = 24, points: int = 300):
    from .targets import c_to_f
    rows = await request.app.state.store.readings_since(min(max(hours, 1), 24 * 30))
    step = max(1, len(rows) // max(50, min(points, 3000)))
    pts = [{"t": r["t"], "temp_c": r["temp_c"], "temp_f": c_to_f(r["temp_c"]) if r["temp_c"] is not None else None,
            "humidity": r["humidity"], "vpd_kpa": r["vpd_kpa"], "light_on": bool(r["light_on"]) if r["light_on"] is not None else None}
           for r in rows[::step]]
    return {"points": pts}


@router.get("/devices/history", dependencies=auth)
async def devices_history(request: Request, hours: float = 168):
    rows = await request.app.state.store.device_log_since(min(max(hours, 1), 24 * 30))
    return {"events": rows}


@router.get("/energy", dependencies=auth)
async def energy(request: Request):
    st = request.app.state
    c: Controller = st.controller
    settings = await c.settings()
    dmap = await st.store.get_device_map()
    devices, today, month = [], 0.0, 0.0
    any_today = any_month = False
    for role in SWITCH_ROLES:
        if not dmap.get(role):
            continue
        t, mo = c.energy_kwh(role, dmap, "today"), c.energy_kwh(role, dmap, "month")
        if t is not None:
            today += t; any_today = True
        if mo is not None:
            month += mo; any_month = True
        devices.append({"role": role, "label": ROLE_BY_NAME[role].label, "power_w": c.power_w(role, dmap), "today_kwh": t, "month_kwh": mo})
    price = settings.get("price_per_kwh")
    price = float(price) if price not in (None, "") else None
    return {
        "devices": devices,
        "today_kwh": round(today, 3) if any_today else None,
        "month_kwh": round(month, 3) if any_month else None,
        "power_w": round(sum(d["power_w"] for d in devices if d["power_w"] is not None), 1) if any(d["power_w"] is not None for d in devices) else None,
        "price_per_kwh": price,
        "currency": settings.get("currency") or "CAD",
        "today_cost": round(today * price, 2) if (price is not None and any_today) else None,
        "month_cost": round(month * price, 2) if (price is not None and any_month) else None,
    }


@router.get("/backup", dependencies=auth)
async def backup(request: Request):
    """Zip of the database plus photos (camera timelapse frames are excluded; they regenerate)."""
    import zipfile
    st = request.app.state
    buf = io.BytesIO()
    db_path = Path(st.store.path)
    # a consistent copy of the live SQLite file
    import sqlite3
    tmp = db_path.with_suffix(".backup.sqlite")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(tmp)
    with dst:
        src.backup(dst)
    src.close(); dst.close()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "grow_brain.sqlite")
        for p in sorted(Path(st.photo_dir).glob("*.jpg")):
            z.write(p, f"photos/{p.name}")
    tmp.unlink(missing_ok=True)
    buf.seek(0)
    name = f"growop-backup-{datetime.now().strftime('%Y-%m-%d')}.zip"
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------ devices

def _roles_api() -> list[dict]:
    return [{"role": r.role, "label": r.label, "kind": r.kind, "required": r.required, "description": r.description} for r in ROLES]


@router.get("/devices", dependencies=auth)
async def devices(request: Request):
    return {"devices": await request.app.state.controller.device_statuses(), "roles": _roles_api()}


@router.put("/devices/{role}", dependencies=auth)
async def map_device(role: str, body: DeviceMapUpdate, request: Request):
    st = request.app.state
    if role not in ROLE_BY_NAME:
        raise HTTPException(404, f"Unknown role {role}")
    await st.store.set_device(role, body.entity_id)
    st.controller.last_reasons.pop(role, None)
    await st.store.add_event("info", "system", f"{ROLE_BY_NAME[role].label} mapped to {body.entity_id or 'nothing'}")
    return next(d for d in await st.controller.device_statuses() if d["role"] == role)


@router.post("/devices/{role}/override", dependencies=auth)
async def override(role: str, body: OverrideRequest, request: Request):
    st = request.app.state
    if role not in ROLE_BY_NAME or ROLE_BY_NAME[role].kind != "switch":
        raise HTTPException(404, f"Unknown switch role {role}")
    await st.store.set_override(role, body.mode, body.minutes)
    await st.store.add_event("info", "device", f"{ROLE_BY_NAME[role].label} set to {body.mode}" +
                             (f" for {body.minutes} min" if body.minutes and body.mode != "auto" else ""))
    if body.mode in ("on", "off"):
        dmap = await st.store.get_device_map()
        if dmap.get(role):
            await st.controller.ha.turn(dmap[role], body.mode == "on")
            st.controller.states.setdefault(dmap[role], {})["state"] = body.mode
            st.controller.last_switched[role] = utcnow()
    return next(d for d in await st.controller.device_statuses() if d["role"] == role)


@router.get("/ha/entities", dependencies=auth)
async def ha_entities(request: Request):
    try:
        return {"entities": await request.app.state.controller.ha.list_candidates()}
    except Exception as e:
        raise HTTPException(502, f"Home Assistant not reachable: {e}")


@router.post("/ha/automap", dependencies=auth)
async def ha_automap(request: Request):
    st = request.app.state
    try:
        ents = await st.controller.ha.list_candidates()
    except Exception as e:
        raise HTTPException(502, f"Home Assistant not reachable: {e}")
    mapping = automap(ents)
    for role, eid in mapping.items():
        await st.store.set_device(role, eid)
    await st.store.add_event("info", "system", "Auto-mapped devices: " + ", ".join(f"{ROLE_BY_NAME[r].label}={e}" for r, e in mapping.items()))
    return {"devices": await st.controller.device_statuses(), "roles": _roles_api()}


# ------------------------------------------------------------------ grow profile / stage / targets

@router.get("/grow", dependencies=auth)
async def get_grow(request: Request):
    return await request.app.state.controller.profile()


@router.put("/grow", dependencies=auth)
async def put_grow(body: GrowProfileUpdate, request: Request):
    st = request.app.state
    profile = GrowProfile(**await st.controller.profile())
    updated = profile.model_copy(update=body.model_dump(exclude_none=True))
    if updated.start_date and not updated.stage_started:
        updated.stage_started = updated.start_date
    await st.store.set_kv("grow_profile", updated.model_dump())
    return updated.model_dump()


@router.post("/grow/stage", dependencies=auth)
async def set_stage(body: StageChange, request: Request):
    st = request.app.state
    profile = GrowProfile(**await st.controller.profile())
    today = datetime.now(st.controller.tz(await st.controller.settings())).date().isoformat()
    profile.stage = body.stage
    profile.stage_started = today
    if body.stage == "flower" and not profile.flower_start_date:
        profile.flower_start_date = today
    if not profile.start_date:
        profile.start_date = today
    await st.store.set_kv("grow_profile", profile.model_dump())
    old = await st.store.get_kv("targets_override", None) or {}
    await st.store.del_kv("targets_override")
    if old.get("light_on_time"):
        await st.store.set_kv("targets_override", {"values": {}, "source": "stage_default", "light_on_time": old["light_on_time"]})
    await st.store.add_event("info", "system", f"Stage changed to {body.stage}; targets reset to stage defaults")
    return profile.model_dump()


@router.get("/targets", dependencies=auth)
async def get_targets(request: Request):
    t, _, _ = await request.app.state.controller.effective_targets()
    return t.to_api()


@router.put("/targets", dependencies=auth)
async def put_targets(body: TargetsUpdate, request: Request):
    st = request.app.state
    override = await st.store.get_kv("targets_override", None) or {"values": {}, "source": "manual"}
    vals = dict(override.get("values", {}))
    upd = body.model_dump(exclude_none=True)
    if "light_on_time" in upd:
        override["light_on_time"] = upd.pop("light_on_time")
    vals.update(upd)
    await st.store.set_kv("targets_override", {"values": vals, "source": "manual", "light_on_time": override.get("light_on_time", "06:00")})
    t, _, _ = await st.controller.effective_targets()
    await st.store.add_event("info", "system", "Targets edited manually")
    return t.to_api()


@router.delete("/targets", dependencies=auth)
async def reset_targets(request: Request):
    st = request.app.state
    old = await st.store.get_kv("targets_override", None) or {}
    await st.store.del_kv("targets_override")
    if old.get("light_on_time"):
        await st.store.set_kv("targets_override", {"values": {}, "source": "stage_default", "light_on_time": old["light_on_time"]})
    t, _, _ = await st.controller.effective_targets()
    return t.to_api()


# ------------------------------------------------------------------ settings / control

async def _settings_api(request: Request) -> dict:
    st = request.app.state
    s = await st.controller.settings()
    s["model"] = s.get("model") or st.boot.model
    s["advisor_enabled"] = st.advisor.enabled
    try:
        s["notify_services_available"] = await st.controller.ha.list_notify_services()
    except Exception:
        s["notify_services_available"] = []
    return SettingsModel(**s).model_dump()


@router.get("/settings", dependencies=auth)
async def get_settings(request: Request):
    return await _settings_api(request)


@router.put("/settings", dependencies=auth)
async def put_settings(body: SettingsUpdate, request: Request):
    st = request.app.state
    current = await st.store.get_kv("settings", {}) or {}
    upd = body.model_dump(exclude_unset=True)
    if "timezone" in upd:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(upd["timezone"])
        except Exception:
            raise HTTPException(400, f"Unknown timezone {upd['timezone']}")
    current.update(upd)
    await st.store.set_kv("settings", current)
    return await _settings_api(request)


@router.post("/control/pause", dependencies=auth)
async def pause(body: PauseRequest, request: Request):
    st = request.app.state
    until = iso(utcnow() + timedelta(minutes=max(1, min(body.minutes, 720))))
    await st.store.set_kv("control_paused_until", until)
    await st.store.add_event("warn", "system", f"Automation paused for {body.minutes} min (safety limits still active)")
    return {"control_paused_until": until}


@router.post("/control/resume", dependencies=auth)
async def resume(request: Request):
    st = request.app.state
    await st.store.del_kv("control_paused_until")
    await st.store.set_kv("standby", False)
    await st.store.add_event("info", "system", "Automation resumed")
    await st.store.resolve_alerts("system", "Automation paused")
    await st.store.resolve_alerts("system", "Tent put in standby")
    return {"control_paused_until": None, "standby": False}


@router.post("/control/standby", dependencies=auth)
async def standby(request: Request):
    """Tent off: every mapped device switches off and stays off until /control/start."""
    st = request.app.state
    await st.store.set_kv("standby", True)
    await st.store.del_kv("control_paused_until")
    dmap = await st.store.get_device_map()
    for role in SWITCH_ROLES:
        eid = dmap.get(role)
        if eid:
            await st.store.set_override(role, "auto", None)
            if await st.controller.ha.turn(eid, False):
                st.controller.states.setdefault(eid, {})["state"] = "off"
                st.controller.last_switched[role] = utcnow()
                st.controller.last_reasons[role] = "tent in standby"
    await st.store.add_event("warn", "system", "Tent put in standby: all devices off until you start it")
    return {"standby": True}


@router.post("/control/start", dependencies=auth)
async def start(request: Request):
    """Back to fully automatic: clears standby, pause and every manual override."""
    st = request.app.state
    await st.store.set_kv("standby", False)
    await st.store.del_kv("control_paused_until")
    for role in SWITCH_ROLES:
        await st.store.set_override(role, "auto", None)
    await st.store.add_event("info", "system", "Tent started: automation fully on, manual overrides cleared")
    await st.store.resolve_alerts("system", "Automation paused")
    await st.store.resolve_alerts("system", "Tent put in standby")
    return {"standby": False, "control_paused_until": None}


# ------------------------------------------------------------------ log

@router.post("/log", dependencies=auth)
async def create_log(body: LogCreate, request: Request):
    st = request.app.state
    plant_id = body.plant_id
    if plant_id is None:
        plants = await st.store.plants()
        plant_id = plants[0]["id"] if len(plants) == 1 else None
    entry = await st.store.add_log_entry(body.kind, body.value, body.unit, body.context, body.note, plant_id)
    advice = None
    if st.advisor.enabled:
        try:
            advice = await st.advisor.advise_on_log(entry)
            entry = await st.store.get_log_entry(entry["id"])
        except AdvisorError as e:
            advice = {"summary": str(e), "steps": [], "urgency": "info", "photo_requests": [], "tasks": []}
    else:
        advice = {"summary": "Logged. (Advisor is off: add an Anthropic API key to get advice.)", "steps": [],
                  "urgency": "info", "photo_requests": [], "tasks": []}
    return {"entry": entry, "advice": advice}


@router.get("/log", dependencies=auth)
async def list_log(request: Request, limit: int = 50):
    return {"entries": await request.app.state.store.log_entries(min(limit, 500))}


# ------------------------------------------------------------------ tasks

@router.get("/tasks", dependencies=auth)
async def list_tasks(request: Request, status: Optional[str] = "open"):
    return {"tasks": await request.app.state.store.tasks(None if status in (None, "all") else status)}


@router.post("/tasks", dependencies=auth)
async def create_task(body: TaskCreate, request: Request):
    return await request.app.state.store.add_task(body.title, body.detail, body.due, body.priority, "user", body.plant_id)


@router.post("/tasks/{tid}/complete", dependencies=auth)
async def complete_task(tid: int, request: Request):
    t = await request.app.state.store.set_task_status(tid, "done")
    if not t:
        raise HTTPException(404, "No such task")
    return t


@router.post("/tasks/{tid}/reopen", dependencies=auth)
async def reopen_task(tid: int, request: Request):
    t = await request.app.state.store.set_task_status(tid, "open")
    if not t:
        raise HTTPException(404, "No such task")
    return t


# ------------------------------------------------------------------ photos

@router.get("/photo-requests", dependencies=auth)
async def photo_requests(request: Request, status: Optional[str] = "open"):
    return {"requests": await request.app.state.store.photo_requests(None if status in (None, "all") else status)}


@router.post("/photo-requests/{rid}/skip", dependencies=auth)
async def skip_photo_request(rid: int, request: Request):
    st = request.app.state
    pr = await st.store.get_photo_request(rid)
    if not pr:
        raise HTTPException(404, "No such photo request")
    await st.store.set_photo_request_status(rid, "skipped")
    return await st.store.get_photo_request(rid)


@router.post("/photos", dependencies=auth)
async def upload_photo(request: Request, image: UploadFile = File(...), request_id: Optional[int] = Form(None),
                       note: Optional[str] = Form(None), plant_id: Optional[int] = Form(None)):
    st = request.app.state
    raw = await image.read()
    if not raw:
        raise HTTPException(400, "Empty image")
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        raise HTTPException(400, "Could not read image")
    im.thumbnail((2000, 2000))
    req = await st.store.get_photo_request(request_id) if request_id else None
    if plant_id is None and req:
        plant_id = req.get("plant_id")
    if plant_id is None:
        plants = await st.store.plants()
        plant_id = plants[0]["id"] if len(plants) == 1 else None
    pid = await st.store.add_photo(request_id, note, "", plant_id)
    photo_dir: Path = st.photo_dir
    path = photo_dir / f"{pid}.jpg"
    im.save(path, "JPEG", quality=88)
    thumb = im.copy()
    thumb.thumbnail((400, 400))
    thumb.save(photo_dir / f"{pid}_thumb.jpg", "JPEG", quality=80)
    await st.store.db.execute("UPDATE photos SET path=? WHERE id=?", (str(path), pid))
    await st.store.db.commit()

    if st.advisor.enabled:
        try:
            await st.advisor.analyse_photo(pid, path, "image/jpeg", req, note, plant_id)
        except AdvisorError as e:
            await st.store.set_photo_analysis(pid, {"summary": str(e), "health_score": 0, "findings": [], "actions": [],
                                                    "photo_requests": [], "tasks": []})
    else:
        await st.store.set_photo_analysis(pid, {"summary": "Saved. (Advisor is off: add an Anthropic API key to get analysis.)",
                                                "health_score": 0, "findings": [], "actions": [], "photo_requests": [], "tasks": []})
        if req:
            await st.store.set_photo_request_status(req["id"], "done", pid)
    return _photo_api(await st.store.get_photo(pid))


def _photo_api(p: dict) -> dict:
    p = dict(p)
    p.pop("path", None)
    return p


@router.get("/photos", dependencies=auth)
async def list_photos(request: Request, limit: int = 30):
    return {"photos": [_photo_api(p) for p in await request.app.state.store.photos(min(limit, 200))]}


@router.get("/photos/{pid}/image", dependencies=auth)
async def photo_image(pid: int, request: Request):
    p = await request.app.state.store.get_photo(pid)
    if not p or not Path(p["path"]).exists():
        raise HTTPException(404, "No such photo")
    return FileResponse(p["path"], media_type="image/jpeg")


@router.get("/photos/{pid}/thumb", dependencies=auth)
async def photo_thumb(pid: int, request: Request):
    p = await request.app.state.store.get_photo(pid)
    if not p:
        raise HTTPException(404, "No such photo")
    t = Path(p["path"]).with_name(f"{pid}_thumb.jpg")
    if not t.exists():
        raise HTTPException(404, "No thumbnail")
    return FileResponse(t, media_type="image/jpeg")


# ------------------------------------------------------------------ brief / chat

@router.get("/brief", dependencies=auth)
async def get_brief(request: Request):
    return await request.app.state.store.latest_brief()


@router.post("/brief/run", dependencies=auth)
async def run_brief(request: Request):
    st = request.app.state
    if not st.advisor.enabled:
        raise HTTPException(503, "Advisor is off: add your Anthropic API key in the add-on configuration.")
    try:
        return await st.advisor.daily_brief()
    except AdvisorError as e:
        raise HTTPException(502, str(e))


@router.post("/brief/{bid}/read", dependencies=auth)
async def read_brief(bid: int, request: Request):
    await request.app.state.store.mark_brief_read(bid)
    return {"ok": True}


@router.post("/chat", dependencies=auth)
async def chat(body: ChatRequest, request: Request):
    st = request.app.state
    if not st.advisor.enabled:
        raise HTTPException(503, "Advisor is off: add your Anthropic API key in the add-on configuration.")
    if not body.message.strip():
        raise HTTPException(400, "Say something first")
    try:
        return await st.advisor.chat(body.message.strip(), body.plant_id)
    except AdvisorError as e:
        raise HTTPException(502, str(e))


@router.get("/chat", dependencies=auth)
async def chat_history(request: Request, limit: int = 50):
    rows = await request.app.state.store.chat_history(min(limit, 200))
    return {"messages": [{"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]}


@router.delete("/chat", dependencies=auth)
async def clear_chat(request: Request):
    await request.app.state.store.clear_chat()
    return {"ok": True}


# ------------------------------------------------------------------ camera

@router.get("/camera", dependencies=auth)
async def camera_info(request: Request):
    st = request.app.state
    return {"camera": await st.camera.info(), "candidates": st.camera.candidates()}


@router.put("/camera", dependencies=auth)
async def camera_select(body: CameraSelect, request: Request):
    st = request.app.state
    cur = await st.store.get_kv("settings", {}) or {}
    cur["camera_entity"] = body.entity_id or ""
    await st.store.set_kv("settings", cur)
    st.camera._cache = None
    await st.store.add_event("info", "system", f"Tent camera set to {body.entity_id or 'off'}")
    return {"camera": await st.camera.info(), "candidates": st.camera.candidates()}


@router.get("/camera/snapshot", dependencies=auth)
async def camera_snapshot(request: Request):
    data = await request.app.state.camera.snapshot()
    if not data:
        raise HTTPException(503, f"No image from the camera ({request.app.state.camera.last_error or 'not configured'})")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/camera/stream", dependencies=auth)
async def camera_stream(request: Request):
    st = request.app.state
    eid = await st.camera.entity_id()
    if not eid:
        raise HTTPException(404, "No tent camera configured")

    # Open the upstream first so we can mirror its multipart boundary header.
    upstream = st.ha.camera_stream_request(eid)
    r = await upstream.__aenter__()
    if r.status_code != 200:
        await upstream.__aexit__(None, None, None)
        raise HTTPException(502, f"Home Assistant camera stream returned {r.status_code}")

    async def passthrough():
        try:
            async for chunk in r.aiter_bytes():
                yield chunk
        finally:
            await upstream.__aexit__(None, None, None)

    return StreamingResponse(passthrough(), media_type=r.headers.get("content-type", "multipart/x-mixed-replace"))


@router.get("/camera/frames", dependencies=auth)
async def camera_frames(request: Request, days: float = 7):
    rows = await request.app.state.store.frames(min(max(days, 0.1), 14))
    return {"frames": [{"id": r["id"], "t": r["t"], "lights_on": bool(r["lights_on"]) if r["lights_on"] is not None else None,
                        "url": f"/api/camera/frames/{r['id']}"} for r in rows]}


@router.get("/camera/frames/{fid}", dependencies=auth)
async def camera_frame(fid: int, request: Request):
    fr = await request.app.state.store.get_frame(fid)
    if not fr or not Path(fr["path"]).exists():
        raise HTTPException(404, "No such frame")
    return FileResponse(fr["path"], media_type="image/jpeg")


@router.post("/camera/analyse", dependencies=auth)
async def camera_analyse(body: CameraAnalyse, request: Request):
    """Take a fresh snapshot and run it through the advisor like an uploaded photo."""
    st = request.app.state
    data = await st.camera.snapshot(max_age_s=0)
    if not data:
        raise HTTPException(503, f"No image from the camera ({st.camera.last_error or 'not configured'})")
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((2000, 2000))
    note = (body.note or "").strip() or None
    pid = await st.store.add_photo(None, f"Tent camera snapshot{(' – ' + note) if note else ''}", "", body.plant_id)
    path = st.photo_dir / f"{pid}.jpg"
    im.save(path, "JPEG", quality=88)
    thumb = im.copy(); thumb.thumbnail((400, 400)); thumb.save(st.photo_dir / f"{pid}_thumb.jpg", "JPEG", quality=80)
    await st.store.db.execute("UPDATE photos SET path=? WHERE id=?", (str(path), pid))
    await st.store.db.commit()
    if not st.advisor.enabled:
        await st.store.set_photo_analysis(pid, {"summary": "Saved. (Advisor is off: add an Anthropic API key to get analysis.)",
                                                "health_score": 0, "findings": [], "actions": [], "photo_requests": [], "tasks": []})
    else:
        try:
            await st.advisor.analyse_photo(pid, path, "image/jpeg", None, "Live snapshot from the fixed tent camera (wide view of the whole tent)." + (f" Grower's note: {note}" if note else ""), body.plant_id)
        except AdvisorError as e:
            await st.store.set_photo_analysis(pid, {"summary": str(e), "health_score": 0, "findings": [], "actions": [], "photo_requests": [], "tasks": []})
    return _photo_api(await st.store.get_photo(pid))


# ------------------------------------------------------------------ events

@router.get("/events", dependencies=auth)
async def events(request: Request, limit: int = 50):
    return {"events": await request.app.state.store.events(min(limit, 500))}
