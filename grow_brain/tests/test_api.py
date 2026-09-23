"""HTTP API tests with an in-process app, a real SQLite store and a stubbed Home Assistant."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from grow_brain.camera import CameraService
from grow_brain.controller import Controller
from grow_brain.main import create_app
from grow_brain.notify import Notifier
from grow_brain.store import Store


class FakeHA:
    def __init__(self):
        self.connected = True
        self.last_error = None
        now = datetime.now(timezone.utc).isoformat()
        self.state = {
            "switch.grow_light": "on", "switch.grow_exhaust": "off", "switch.grow_humidifier": "on",
        }
        self.sensors = {"sensor.tent_temperature": ("24.0", "°C", "temperature"), "sensor.tent_humidity": ("55.0", "%", "humidity")}
        self.calls = []
        self._now = now
        self.light_w = 118.0
        self.humid_w = 0.0
        self.exhaust_total_kwh = 100.0
        self.notifications = []

    async def ping(self):
        return True

    async def get_states(self):
        out = [{"entity_id": e, "state": s, "attributes": {"friendly_name": e}, "last_updated": self._now, "last_reported": self._now}
               for e, s in self.state.items()]
        out.append({"entity_id": "camera.wyze_cam_man_cave", "state": "idle", "attributes": {"friendly_name": "Wyze Cam Man cave"},
                    "last_updated": self._now, "last_reported": self._now})
        for base, w in (("grow_light", self.light_w), ("grow_humidifier", self.humid_w)):
            out.append({"entity_id": f"sensor.{base}_current_consumption", "state": str(w), "attributes": {"unit_of_measurement": "W"},
                        "last_updated": self._now, "last_reported": self._now})
            out.append({"entity_id": f"sensor.{base}_today_s_consumption", "state": "1.5", "attributes": {"unit_of_measurement": "kWh"},
                        "last_updated": self._now, "last_reported": self._now})
        # a Matter-style cumulative meter on the exhaust plug
        out.append({"entity_id": "sensor.grow_exhaust_power", "state": "24.0", "attributes": {"unit_of_measurement": "W"},
                    "last_updated": self._now, "last_reported": self._now})
        out.append({"entity_id": "sensor.grow_exhaust_energy", "state": str(self.exhaust_total_kwh), "attributes": {"unit_of_measurement": "kWh"},
                    "last_updated": self._now, "last_reported": self._now})
        for e, (v, u, dc) in self.sensors.items():
            out.append({"entity_id": e, "state": v, "attributes": {"unit_of_measurement": u, "device_class": dc, "friendly_name": e},
                        "last_updated": self._now, "last_reported": self._now})
        return out

    async def camera_image(self, entity_id):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (640, 480), (30, 120, 40)).save(buf, "JPEG")
        return buf.getvalue()

    async def turn(self, entity_id, on):
        self.calls.append((entity_id, on))
        self.state[entity_id] = "on" if on else "off"
        return True

    async def notify(self, service, message, **k):
        self.notifications.append(message)
        return True

    async def list_notify_services(self):
        return ["notify.mobile_app_test"]

    async def list_candidates(self):
        from grow_brain.devices import suggest_role
        return [{"entity_id": s["entity_id"], "name": s["attributes"].get("friendly_name"), "domain": s["entity_id"].split(".")[0],
                 "state": s["state"], "unit": s["attributes"].get("unit_of_measurement"), "device_class": s["attributes"].get("device_class"),
                 "suggested_role": suggest_role(s["entity_id"], s["attributes"].get("friendly_name"), s["attributes"].get("device_class"), s["attributes"].get("unit_of_measurement"))}
                for s in await self.get_states()]

    async def close(self):
        pass


@pytest.fixture
async def client(tmp_path: Path):
    app = create_app()
    store = Store(tmp_path / "t.sqlite")
    await store.open()
    ha = FakeHA()
    controller = Controller(store, ha, "UTC", Notifier(ha, store))
    app.state.boot = SimpleNamespace(api_key="k", model="claude-opus-5")
    app.state.store = store
    app.state.controller = controller
    app.state.advisor = SimpleNamespace(enabled=False)
    app.state.photo_dir = tmp_path
    app.state.ha = ha
    app.state.camera = CameraService(store, ha, controller, tmp_path / "cam")
    for role, eid in {"light": "switch.grow_light", "exhaust_fan": "switch.grow_exhaust", "humidifier": "switch.grow_humidifier",
                      "temperature_sensor": "sensor.tent_temperature", "humidity_sensor": "sensor.tent_humidity"}.items():
        await store.set_device(role, eid)
    await store.set_kv("grow_profile", {"stage": "seedling", "start_date": "2026-09-19", "stage_started": "2026-09-19"})
    await controller.cycle()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers={"X-API-Key": "k"}) as c:
        yield c, ha, store, controller
    await store.close()


async def test_health_and_auth(client):
    c, *_ = client
    assert (await c.get("/api/health")).json()["ok"] is True
    assert (await c.get("/api/status", headers={"X-API-Key": "wrong"})).status_code == 401


async def test_status_shape(client):
    c, ha, store, controller = client
    s = (await c.get("/api/status")).json()
    assert s["standby"] is False and s["sensor"]["temp_c"] == 24.0 and s["sensor"]["stale"] is False
    assert s["assessment"]["level"] in ("good", "warn", "alert")
    assert {d["role"] for d in s["devices"] if d["entity_id"]} == {"light", "exhaust_fan", "humidifier", "temperature_sensor", "humidity_sensor"}
    assert s["light"]["schedule"] == "18/6"


async def test_standby_then_start(client):
    c, ha, store, controller = client
    await c.post("/api/devices/light/override", json={"mode": "on", "minutes": 60})
    r = await c.post("/api/control/standby")
    assert r.json() == {"standby": True}
    assert ha.state["switch.grow_light"] == "off" and ha.state["switch.grow_humidifier"] == "off"
    assert await store.get_overrides() == {}
    s = (await c.get("/api/status")).json()
    assert s["standby"] is True and s["assessment"]["level"] == "standby" and s["assessment"]["headline"] == "Tent is off"
    # the control loop keeps everything off while in standby (once the min-switch interval has passed)
    ha.state["switch.grow_light"] = "on"
    controller.last_switched.clear()
    await controller.cycle()
    assert ha.state["switch.grow_light"] == "off"
    r = await c.post("/api/control/start")
    assert r.json()["standby"] is False
    controller.last_switched.clear()
    await controller.cycle()
    from grow_brain.controller import light_window
    scheduled_on, _ = light_window(datetime.now(timezone.utc), "06:00", 18)
    assert ha.state["switch.grow_light"] == ("on" if scheduled_on else "off")
    assert (await c.get("/api/status")).json()["standby"] is False


async def test_plan_endpoint(client):
    c, *_ = client
    p = (await c.get("/api/plan")).json()
    assert p["current_phase"] in ("germination", "seedling") and len(p["phases"]) == 9
    assert sum(1 for x in p["phases"] if x["status"] == "current") == 1


async def test_devices_and_history(client):
    c, ha, store, controller = client
    r = await c.put("/api/devices/heater", json={"entity_id": "switch.grow_exhaust"})
    assert r.json()["entity_id"] == "switch.grow_exhaust"
    r = await c.put("/api/devices/heater", json={"entity_id": None})
    assert r.json()["entity_id"] is None
    h = (await c.get("/api/history", params={"hours": 1})).json()
    assert len(h["points"]) >= 1 and h["points"][0]["temp_c"] == 24.0


async def test_plants_crud_and_per_plant_data(client):
    c, ha, store, controller = client
    p1 = (await c.post("/api/plants", json={"name": "Levi's plant", "owner": "Levi", "start_date": "2026-09-19"})).json()
    p2 = (await c.post("/api/plants", json={"name": "Dad's plant", "owner": "Dad", "start_date": "2026-09-21", "medium": "coco"})).json()
    assert p1["id"] != p2["id"] and p2["medium"] == "coco" and p1["day_total"] >= 0
    ps = (await c.get("/api/plants")).json()["plants"]
    assert [p["name"] for p in ps] == ["Levi's plant", "Dad's plant"]
    assert len((await c.get("/api/status")).json()["plants"]) == 2
    # per-plant plan uses that plant's start date
    plan2 = (await c.get("/api/plan", params={"plant_id": p2["id"]})).json()
    assert plan2["plant_id"] == p2["id"] and plan2["start_date"] == "2026-09-21"
    # per-plant log / tasks
    e = (await c.post("/api/log", json={"plant_id": p2["id"], "kind": "ph", "value": 6.5, "unit": "pH"})).json()["entry"]
    assert e["plant_id"] == p2["id"]
    t = (await c.post("/api/tasks", json={"plant_id": p1["id"], "title": "Water"})).json()
    tt = (await c.post("/api/tasks", json={"title": "Duct the exhaust"})).json()
    assert t["plant_id"] == p1["id"] and tt["plant_id"] is None
    assert {x["plant_id"] for x in (await c.get("/api/tasks")).json()["tasks"]} == {p1["id"], None}
    r = await c.put(f"/api/plants/{p2['id']}", json={"owner": "Dad S.", "notify_service": "notify.mobile_app_x"})
    assert r.json()["owner"] == "Dad S." and r.json()["notify_service"] == "notify.mobile_app_x"
    assert (await c.delete(f"/api/plants/{p2['id']}")).json() == {"ok": True}
    assert [p["id"] for p in (await c.get("/api/plants")).json()["plants"]] == [p1["id"]]
    assert (await c.get(f"/api/plants/999")).status_code in (404, 405)


async def test_camera_auto_select_snapshot_frames_and_analyse(client):
    c, ha, store, controller = client
    info = (await c.get("/api/camera")).json()
    assert info["camera"]["entity_id"] == "camera.wyze_cam_man_cave" and info["camera"]["name"] == "Wyze Cam Man cave"
    assert (await c.get("/api/status")).json()["camera"]["entity_id"] == "camera.wyze_cam_man_cave"
    r = await c.get("/api/camera/snapshot")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    cam = c._transport.app.state.camera
    fr = await cam.capture_frame()
    assert fr and (await c.get("/api/camera/frames")).json()["frames"][0]["id"] == fr["id"]
    assert (await c.get(f"/api/camera/frames/{fr['id']}")).status_code == 200
    p = (await c.post("/api/camera/analyse", json={"plant_id": None})).json()
    assert p["id"] and "camera" in p["note"].lower() and p["analysis"]["summary"].startswith("Saved")
    # turning it off
    assert (await c.put("/api/camera", json={"entity_id": None})).json()["camera"] is None
    assert (await c.get("/api/camera/snapshot")).status_code == 503


async def test_power_energy_offsets_history_backup(client):
    c, ha, store, controller = client
    s = (await c.get("/api/status")).json()
    byrole = {d["role"]: d for d in s["devices"]}
    assert byrole["light"]["power_w"] == 118.0 and byrole["humidifier"]["power_w"] == 0.0 and byrole["exhaust_fan"]["power_w"] == 24.0
    e = (await c.get("/api/energy")).json()
    assert e["today_kwh"] == 3.0 and e["today_cost"] is None
    await c.put("/api/settings", json={"price_per_kwh": 0.2, "currency": "CAD", "temp_offset_c": -1.0, "humidity_offset": 2.5})
    e = (await c.get("/api/energy")).json()
    assert e["today_cost"] == 0.6 and e["currency"] == "CAD"
    # the fake tent's humidifier is on: pretend the controller started that pulse a moment ago so it keeps running
    ha.state["switch.grow_humidifier"] = "on"
    controller.last_switched["humidifier"] = datetime.now(timezone.utc)
    await controller.cycle()
    s = (await c.get("/api/status")).json()
    assert s["sensor"]["temp_c"] == 23.0 and s["sensor"]["humidity"] == 57.5  # offsets applied to 24.0 / 55.0
    # power watchdog: humidifier on for > 3 min drawing 0 W → warn + notification
    await store.set_kv("settings", {**(await store.get_kv("settings")), "notify_service": "notify.test"})
    from datetime import timedelta
    controller._on_since["humidifier"] = controller._on_since.get("humidifier", datetime.now(timezone.utc)) - timedelta(minutes=5)
    await controller.cycle()
    evs = (await c.get("/api/events", params={"limit": 10})).json()["events"]
    assert any("Humidifier is switched on but drawing only 0 W" in e["message"] for e in evs)
    assert any("Humidifier" in n for n in ha.notifications)
    # devices history + history points
    dh = (await c.get("/api/devices/history", params={"hours": 24})).json()
    assert isinstance(dh["events"], list)
    h = (await c.get("/api/history", params={"hours": 24, "points": 1000})).json()
    assert len(h["points"]) >= 1
    # backup is a zip containing the database
    r = await c.get("/api/backup")
    import io, zipfile
    assert r.status_code == 200 and "grow_brain.sqlite" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()


async def test_cumulative_energy_meter_baselines(client):
    c, ha, store, controller = client
    e = (await c.get("/api/energy")).json()
    ex = next(d for d in e["devices"] if d["role"] == "exhaust_fan")
    assert ex["power_w"] == 24.0 and ex["today_kwh"] == 0.0  # baseline just recorded at 100.0
    ha.exhaust_total_kwh = 100.75
    await controller.cycle()
    ex = next(d for d in (await c.get("/api/energy")).json()["devices"] if d["role"] == "exhaust_fan")
    assert ex["today_kwh"] == 0.75 and ex["month_kwh"] == 0.75
    assert (await store.get_kv("energy_baselines"))["exhaust_fan:today"]["kwh"] == 100.0


async def test_alerts_resolve_on_recovery(client):
    c, ha, store, controller = client
    await store.add_event("alert", "system", "Cannot reach Home Assistant: 502")
    assert any("Cannot reach" in a["message"] for a in (await c.get("/api/status")).json()["alerts"])
    controller._ha_fail_reported = True
    controller.ha_ok = False  # as the real failure path sets it
    await controller.cycle()  # HA answers → "connection restored" → the alert is resolved
    assert not any("Cannot reach" in a["message"] for a in (await c.get("/api/status")).json()["alerts"])
    evs = (await c.get("/api/events", params={"limit": 5})).json()["events"]
    assert any(e["message"] == "Home Assistant connection restored" for e in evs)
    await c.post("/api/control/pause", json={"minutes": 5})
    assert any("paused" in a["message"] for a in (await c.get("/api/status")).json()["alerts"])
    await c.post("/api/control/resume")
    assert not any("paused" in a["message"] for a in (await c.get("/api/status")).json()["alerts"])


async def test_stale_ha_alert_clears_on_first_good_cycle(client):
    c, ha, store, controller = client
    await store.add_event("alert", "system", "Cannot reach Home Assistant: 502 (from before a restart)")
    controller.ha_ok = False  # simulate a fresh process
    await controller.cycle()
    assert not any("Cannot reach" in a["message"] for a in (await c.get("/api/status")).json()["alerts"])


async def test_usage_qr_and_nudges(client):
    c, ha, store, controller = client
    await store.add_usage("brief", "claude-opus-5", 8000, 6000, 0, 500, 0.0555)
    u = (await c.get("/api/usage")).json()
    assert u["month"]["calls"] == 1 and u["month"]["usd"] == 0.06 and "brief" in u["month"]["by_kind"]
    assert (await c.get("/api/settings")).json()["advisor_month_usd"] == 0.06
    r = await c.get("/api/setup-qr.png", params={"url": "http://192.168.2.67:8099"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"
    # a photo request open for 3 days gets one nudge to the plant owner, and not again within a day
    p = await store.add_plant(name="Levi's plant", owner="Levi", notify_service="notify.levi")
    pr = await store.add_photo_request("Top of canopy", "From above", "check", p["id"])
    await store.db.execute("UPDATE photo_requests SET created_at=? WHERE id=?", ("2026-01-01T00:00:00Z", pr["id"]))
    await store.db.commit()
    from grow_brain.main import _nudge_tick
    app_state = c._transport.app.state
    app_state.notifier = controller.notifier
    await _nudge_tick(app_state)
    assert any("Still waiting for a photo" in n for n in ha.notifications)
    n_before = len(ha.notifications)
    await store.set_kv("last_nudge_hour", None)
    await _nudge_tick(app_state)
    assert len(ha.notifications) == n_before  # nudged_at set → no second nudge yet


async def test_climate_diagnosis_when_the_light_is_too_hot(client):
    c, ha, store, controller = client
    from datetime import timedelta
    from grow_brain.store import iso, utcnow
    # last hour: exhaust on 30 of every 60 minutes, tent parked at the top of the seedling band, humidity low
    now = utcnow()
    for k in range(6):
        await store.db.execute("INSERT INTO device_log(t, role, state, reason) VALUES(?,?,?,?)",
                               (iso(now - timedelta(minutes=60 - k * 10)), "exhaust_fan", "on" if k % 2 == 0 else "off", "test"))
    for k in range(60):
        await store.db.execute("INSERT INTO readings(t, temp_c, humidity, vpd_kpa, co2, light_on) VALUES(?,?,?,?,?,?)",
                               (iso(now - timedelta(minutes=60 - k)), 27.2, 50.0, 1.7, None, 1))
    await store.db.commit()
    assert 0.45 <= (await controller.exhaust_duty(1.0)) <= 0.55
    await c.put("/api/targets", json={"light_hours": 24})   # lights on whatever the wall clock says
    ha.state["switch.grow_light"] = "on"
    controller._climate_checked_at = None
    await controller.cycle()
    evs = (await c.get("/api/events", params={"limit": 20})).json()["events"]
    hit = [e for e in evs if e["message"].startswith("Can't hold the climate")]
    assert hit and "dim it or raise it" in hit[0]["message"] and "humidity" in hit[0]["message"]
    assert (await c.get("/api/status")).json()["exhaust_duty_1h"] >= 0.45


async def test_humidifier_tank_tracking(client):
    c, ha, store, controller = client
    from datetime import timedelta
    ha.state["switch.grow_humidifier"] = "on"
    controller.last_switched["humidifier"] = datetime.now(timezone.utc)
    controller.last_cycle_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    await controller.cycle()
    tank = (await c.get("/api/status")).json()["humidifier_tank"]
    assert 0.005 <= tank["run_hours_since_refill"] <= 0.02 and tank["tank_hours"] == 4.0 and tank["refill_task_id"] is None
    # 3.3 h of misting on a 4 h tank → a refill task and a phone notification, once
    await store.set_kv("settings", {**(await store.get_kv("settings") or {}), "notify_service": "notify.test"})
    controller._tank["run_s"] = 3.3 * 3600
    await controller.cycle()
    await controller.cycle()
    tasks = (await c.get("/api/tasks")).json()["tasks"]
    refill = [x for x in tasks if x["title"].startswith("Refill the humidifier")]
    assert len(refill) == 1 and refill[0]["priority"] == "high"
    assert sum("Refill the humidifier" in n for n in ha.notifications) == 1
    # ticking the task off restarts the counter
    await c.post(f"/api/tasks/{refill[0]['id']}/complete")
    await controller.cycle()
    tank = (await c.get("/api/status")).json()["humidifier_tank"]
    assert tank["run_hours_since_refill"] < 0.02 and tank["refill_task_id"] is None
    # the setting is adjustable
    await c.put("/api/settings", json={"humidifier_tank_hours": 2.5})
    assert (await c.get("/api/status")).json()["humidifier_tank"]["tank_hours"] == 2.5
