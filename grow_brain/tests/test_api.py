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
        out.append({"entity_id": "camera.tent_cam", "state": "idle", "attributes": {"friendly_name": "Tent cam"},
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
    assert info["camera"]["entity_id"] == "camera.tent_cam" and info["camera"]["name"] == "Tent cam"
    assert (await c.get("/api/status")).json()["camera"]["entity_id"] == "camera.tent_cam"
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
    st = (await c.get("/api/status")).json()
    assert st["control_paused_until"] and not any("paused" in a["message"] for a in st["alerts"])   # a choice, not a problem
    await c.post("/api/control/resume")
    assert (await c.get("/api/status")).json()["control_paused_until"] is None


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
    r = await c.get("/api/setup-qr.png", params={"url": "http://192.168.1.50:8099"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"
    # a photo request open for 3 days gets one nudge to the plant owner, and not again within a day
    p = await store.add_plant(name="Levi's plant", owner="Levi", notify_service="notify.levi")
    pr = await store.add_photo_request("Top of canopy", "From above", "check", p["id"])
    from datetime import timedelta
    from grow_brain.store import iso
    three_days_ago = iso(datetime.now(timezone.utc) - timedelta(days=3))
    await store.db.execute("UPDATE photo_requests SET created_at=? WHERE id=?", (three_days_ago, pr["id"]))
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
    assert hit and "turn the dimmer down" in hit[0]["message"] and "humidity" in hit[0]["message"]
    assert (await c.get("/api/status")).json()["exhaust_duty_1h"] >= 0.45


async def test_climate_warning_left_by_an_older_version_is_cleared(client):
    c, ha, store, controller = client
    from datetime import timedelta
    from grow_brain.store import iso, utcnow
    # raised before the add-on remembered its warnings across restarts: no flag says it's open
    await store.add_event("warn", "climate", "Can't hold the climate: the exhaust ran 45% of the last hour")
    now = utcnow()
    await store.db.execute("INSERT INTO device_log(t, role, state, reason) VALUES(?,?,?,?)",
                           (iso(now - timedelta(minutes=50)), "exhaust_fan", "off", "test"))
    for k in range(40):
        await store.db.execute("INSERT INTO readings(t, temp_c, humidity, vpd_kpa, co2, light_on) VALUES(?,?,?,?,?,?)",
                               (iso(now - timedelta(minutes=40 - k)), 24.5, 63.0, 1.1, None, 1))
    await store.db.commit()
    await c.put("/api/targets", json={"light_hours": 24})
    ha.state["switch.grow_light"] = "on"
    controller._climate_checked_at = None
    await controller.cycle()
    alerts = (await c.get("/api/status")).json()["alerts"]
    assert not any(a["message"].startswith("Can't hold the climate") for a in alerts)


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


# ------------------------------------------------------------------ safety hardening (0.7.0)

async def _plants_with_phones(c):
    for name, owner in (("Levi's plant", "Levi"), ("Dad's plant", "Dad")):
        if len((await c.get("/api/plants")).json()["plants"]) < 2:
            await c.post("/api/plants", json={"name": name, "owner": owner})
    ps = (await c.get("/api/plants")).json()["plants"]
    assert len(ps) == 2
    for p, svc in zip(ps, ("notify.levi_phone", "notify.dad_phone")):
        await c.put(f"/api/plants/{p['id']}", json={"notify_service": svc})
    return ps


async def test_overheat_reaches_every_phone_latches_and_reports_results(client):
    c, ha, store, controller = client
    await _plants_with_phones(c)
    await c.post("/api/control/start")
    ha.state["switch.grow_light"] = "on"
    ha.sensors["sensor.tent_temperature"] = ("35.5", "°C", "temperature")
    ha.notifications.clear()
    await controller.cycle()
    assert ("switch.grow_light", False) in ha.calls and ha.state["switch.grow_exhaust"] == "on"
    assert len(ha.notifications) == 2 and all("OVERHEATING" in n and "Grow light off: done" in n for n in ha.notifications)
    # it cools a little: the cut holds (no flapping at 34.9 °C), and no second alert
    ha.sensors["sensor.tent_temperature"] = ("34.9", "°C", "temperature")
    controller.last_switched.clear()
    await controller.cycle()
    assert ha.state["switch.grow_light"] == "off" and len(ha.notifications) == 2
    assert (await store.get_kv("safety_latch"))["kind"] == "hot"
    # cooled below the release point, but not for long enough yet
    ha.sensors["sensor.tent_temperature"] = ("24.0", "°C", "temperature")
    await controller.cycle()
    assert ha.state["switch.grow_light"] == "off"
    # 15 minutes later: released, lights back on schedule, alert resolved
    from datetime import timedelta
    from grow_brain.store import iso
    controller.safety_latch["since"] = iso(datetime.now(timezone.utc) - timedelta(minutes=16))
    await c.put("/api/targets", json={"light_hours": 24})
    controller.last_switched.clear()
    await controller.cycle()
    assert controller.safety_latch is None and ha.state["switch.grow_light"] == "on"
    alerts = (await c.get("/api/status")).json()["alerts"]
    assert not any(a["message"].startswith("OVERHEATING") for a in alerts)


async def test_standby_still_cuts_a_light_switched_on_by_hand(client):
    c, ha, store, controller = client
    await c.post("/api/control/standby")
    await c.post("/api/devices/light/override", json={"mode": "on"})
    await controller.cycle()
    assert ha.state["switch.grow_light"] == "on"          # the override works normally
    ha.sensors["sensor.tent_temperature"] = ("36.0", "°C", "temperature")
    await controller.cycle()
    assert ha.state["switch.grow_light"] == "off" and ha.state["switch.grow_exhaust"] == "on"


async def test_bad_light_time_is_refused_and_a_stored_one_cannot_stop_the_loop(client):
    c, ha, store, controller = client
    for bad in ("6am", "18.00", "06:00:00", "25:00"):
        r = await c.put("/api/targets", json={"light_on_time": bad})
        assert r.status_code == 422 and "like 06:00" in r.json()["detail"]
    assert (await c.put("/api/targets", json={"light_on_time": "6:30"})).json()["light_on_time"] == "06:30"
    # a bad value that got stored by an older version
    await store.set_kv("targets_override", {"values": {"light_hours": 24}, "source": "manual", "light_on_time": "6pm"})
    await c.post("/api/control/start")
    ha.state["switch.grow_light"] = "on"
    ha.sensors["sensor.tent_temperature"] = ("36.0", "°C", "temperature")
    ha.calls.clear()
    await controller.cycle()
    assert ("switch.grow_light", False) in ha.calls
    assert (await c.get("/api/status")).status_code == 200


async def test_database_failure_does_not_block_switching(client):
    c, ha, store, controller = client
    await c.post("/api/control/start")
    await c.put("/api/targets", json={"light_hours": 24})
    ha.state["switch.grow_light"] = "on"

    async def broken(*a, **k):
        raise RuntimeError("disk full")
    store.add_reading = broken
    store.add_event = broken
    store.log_device = broken
    ha.sensors["sensor.tent_temperature"] = ("36.0", "°C", "temperature")
    ha.calls.clear()
    await controller.cycle()
    assert ("switch.grow_light", False) in ha.calls
    assert "disk full" in controller.last_error


async def test_null_settings_cannot_disable_safety(client):
    c, ha, store, controller = client
    await store.set_kv("settings", {"safety_temp_max_c": None, "control_interval_s": None, "min_switch_interval_s": 0})
    s = await controller.settings()
    assert s["safety_temp_max_c"] == 35.0 and s["control_interval_s"] == 30 and s["min_switch_interval_s"] == 30
    r = await c.put("/api/settings", json={"safety_temp_max_c": 95})
    assert r.status_code == 422


async def test_unreachable_plug_and_ignored_commands_are_reported(client):
    c, ha, store, controller = client
    await _plants_with_phones(c)
    await c.post("/api/control/start")
    from datetime import timedelta
    # the humidifier plug drops off Home Assistant while on
    ha.state["switch.grow_humidifier"] = "unavailable"
    await controller.cycle()
    controller._unavail_since["humidifier"] -= timedelta(minutes=5)
    ha.notifications.clear()
    await controller.cycle()
    assert any("Humidifier plug isn't responding" in n and "switch it off at the plug" in n for n in ha.notifications)
    ha.state["switch.grow_humidifier"] = "off"
    await controller.cycle()
    assert not any("Humidifier plug" in a["message"] for a in (await c.get("/api/status")).json()["alerts"])
    # a plug that answers 200 but never actually switches
    real_turn = ha.turn

    async def ignored(entity_id, on):
        ha.calls.append((entity_id, on))
        return True
    ha.turn = ignored
    ha.sensors["sensor.tent_temperature"] = ("36.0", "°C", "temperature")   # forced decisions skip the switch interval
    ha.state["switch.grow_light"] = "on"
    ha.notifications.clear()
    for _ in range(3):
        await controller.cycle()
    assert any("Grow light isn't responding" in n for n in ha.notifications)
    ha.turn = real_turn


async def test_health_reports_a_dead_control_loop(client):
    c, ha, store, controller = client
    assert (await c.get("/api/health")).status_code == 200
    import asyncio

    async def boom():
        raise RuntimeError("x")
    controller._task = asyncio.create_task(boom())
    try:
        await controller._task
    except RuntimeError:
        pass
    r = await c.get("/api/health")
    assert r.status_code == 503 and r.json()["ok"] is False



async def test_quick_log_task_followups_chat_authors_and_refill(client):
    c, ha, store, controller = client
    await _plants_with_phones(c)
    ps = (await c.get("/api/plants")).json()["plants"]
    # logging is instant and free unless the advisor is asked
    r = (await c.post("/api/log", json={"kind": "water", "value": 0.05, "unit": "L", "plant_id": ps[0]["id"]})).json()
    assert "next daily brief" in r["advice"]["summary"]
    # ticking "Plant ... seed" records the planting, and every planting gets its dome reminder
    t = (await c.post("/api/tasks", json={"title": "Plant Levi's seed when its root shows", "plant_id": ps[0]["id"]})).json()
    await c.post(f"/api/tasks/{t['id']}/complete")
    assert any(e["kind"] == "planted" for e in (await c.get("/api/log")).json()["entries"])
    def domes():
        return [x for x in tasks_now if x["title"].startswith("Take the dome off")]
    tasks_now = (await c.get("/api/tasks")).json()["tasks"]
    assert [x["title"] for x in domes()] == ["Take the dome off Levi's plant"]
    # ...a dome task for the same plant doesn't add a second copy
    d0 = (await c.post("/api/tasks", json={"title": "Put a clear dome over Levi's cup", "plant_id": ps[0]["id"]})).json()
    await c.post(f"/api/tasks/{d0['id']}/complete")
    tasks_now = (await c.get("/api/tasks")).json()["tasks"]
    assert len(domes()) == 1
    # a dome put on Dad's cup schedules taking it off; an Undo right after the tick takes that back with its log line
    d = (await c.post("/api/tasks", json={"title": "Put a clear dome over Dad's cup", "plant_id": ps[1]["id"]})).json()
    await c.post(f"/api/tasks/{d['id']}/complete")
    tasks_now = (await c.get("/api/tasks")).json()["tasks"]
    assert "Take the dome off Dad's plant" in [x["title"] for x in domes()]
    await c.post(f"/api/tasks/{d['id']}/reopen")
    tasks_now = (await c.get("/api/tasks")).json()["tasks"]
    assert d["title"] in [x["title"] for x in tasks_now] and [x["title"] for x in domes()] == ["Take the dome off Levi's plant"]
    assert not any((e.get("note") or "") == f"Done: {d['title']}" for e in (await c.get("/api/log")).json()["entries"])
    # checking on the dome is not putting one on
    for title in ("Check the dome for condensation", "Check the dome for condensation on the lid"):
        k = (await c.post("/api/tasks", json={"title": title, "plant_id": ps[1]["id"]})).json()
        await c.post(f"/api/tasks/{k['id']}/complete")
    tasks_now = (await c.get("/api/tasks")).json()["tasks"]
    assert [x["title"] for x in domes()] == ["Take the dome off Levi's plant"]
    # logging a planting from the Log tab does the same for Dad's plant
    await c.post("/api/log", json={"kind": "planted", "plant_id": ps[1]["id"]})
    tasks_now = (await c.get("/api/tasks")).json()["tasks"]
    assert sorted(x["title"] for x in domes()) == ["Take the dome off Dad's plant", "Take the dome off Levi's plant"]
    # transplanting while still a seedling asks for the stage change
    await c.post("/api/log", json={"kind": "transplant", "plant_id": ps[0]["id"]})
    assert any(x["title"] == "Switch the stage to Veg" for x in (await c.get("/api/tasks")).json()["tasks"])
    # chat rows carry their author even from the old "[Name] " format
    await store.add_chat("user", "[Dad] how's my plant?")
    msgs = (await c.get("/api/chat")).json()["messages"]
    assert msgs[-1]["author"] == "Dad" and msgs[-1]["content"] == "how's my plant?"
    # refill button
    controller._tank["run_s"] = 3 * 3600
    tank = (await c.post("/api/humidifier/refilled")).json()
    assert tank["run_hours_since_refill"] == 0 and tank["hours_left"] == 4.0


async def test_device_mapping_and_camera_are_restricted(client):
    c, ha, store, controller = client
    assert (await c.put("/api/devices/humidifier", json={"entity_id": "cover.garage_door"})).status_code == 422
    assert (await c.put("/api/devices/temperature_sensor", json={"entity_id": "switch.x"})).status_code == 422
    assert (await c.put("/api/camera", json={"entity_id": "switch.x"})).status_code == 422


async def test_brief_read_flags_are_per_phone(client):
    c, ha, store, controller = client
    await store.db.execute("INSERT INTO briefs(created_at, json) VALUES('2026-09-23T12:00:00Z', '{}')")
    await store.db.commit()
    bid = (await (await store.db.execute("SELECT MAX(id) AS i FROM briefs")).fetchone())["i"]
    await c.post(f"/api/brief/{bid}/read", headers={"X-Device-Id": "levi-phone"})
    assert (await c.get("/api/status", headers={"X-Device-Id": "levi-phone"})).json()["unread_brief"] is False
    assert (await c.get("/api/status", headers={"X-Device-Id": "dad-phone"})).json()["unread_brief"] is True


async def test_failed_push_is_retried(client):
    c, ha, store, controller = client
    await _plants_with_phones(c)
    real = ha.notify
    calls = {"n": 0}

    async def flaky(service, message, **k):
        calls["n"] += 1
        return False
    ha.notify = flaky
    await controller.notifier.send("safety:test", "test alert", hours=1, everyone=True)
    assert "safety:test" in controller.notifier.pending
    ha.notify = real
    await controller.notifier.flush()
    assert "safety:test" not in controller.notifier.pending and any("test alert" in n for n in ha.notifications)



async def test_week_old_photo_requests_expire_and_nudges_stop_after_three(client):
    c, ha, store, controller = client
    from datetime import timedelta
    from grow_brain.store import iso
    from grow_brain.main import _nudge_tick
    p = await store.add_plant(name="Dad's plant", owner="Dad", notify_service="notify.dad")
    old = await store.add_photo_request("Old one", "x", "y", p["id"])
    await store.db.execute("UPDATE photo_requests SET created_at=? WHERE id=?", (iso(datetime.now(timezone.utc) - timedelta(days=8)), old["id"]))
    live = await store.add_photo_request("Newer", "x", "y", p["id"])
    await store.db.execute("UPDATE photo_requests SET created_at=?, nudge_count=3 WHERE id=?",
                           (iso(datetime.now(timezone.utc) - timedelta(days=4)), live["id"]))
    await store.db.commit()
    st = c._transport.app.state
    st.notifier = controller.notifier
    ha.notifications.clear()
    await _nudge_tick(st)
    assert (await store.get_photo_request(old["id"]))["status"] == "expired"
    assert not any("Newer" in n for n in ha.notifications)


async def test_settings_reply_includes_budget_and_models(client):
    c, ha, store, controller = client
    s = (await c.get("/api/settings")).json()
    assert s["advisor_budget_usd"] == 40.0 and s["humidifier_tank_hours"] == 4.0 and "claude-opus-5" in s["models_available"]
    s = (await c.put("/api/settings", json={"advisor_budget_usd": 25})).json()
    assert s["advisor_budget_usd"] == 25


async def test_refill_after_a_swap_teaches_the_swap_drop(client):
    c, ha, store, controller = client
    from datetime import timedelta
    from grow_brain.controller import LAG_S, ControlContext, Decision, SensorSnapshot
    from grow_brain.store import utcnow
    from grow_brain.targets import stage_defaults
    t = stage_defaults("seedling")
    now = utcnow()
    ctx = ControlContext(now_local=now, stage="seedling", targets=t, day_targets=t, light_scheduled_on=True, lights_on=True,
                         sensor=SensorSnapshot(24.5, 61.0, 1.0, None, now, False), safety_temp_max_c=35.0,
                         safety_temp_min_c=12.0, exhaust_ducted=True, paused=False)
    # a 90 s fresh-air swap ends, then its 2-minute refill ends
    controller.on_tag["exhaust_fan"] = "exhaust_duty"
    controller._note_switch("exhaust_fan", Decision("exhaust_fan", False, "swap done"), ctx, now - timedelta(seconds=90), now)
    controller.on_tag["humidifier"], controller.on_reading["humidifier"] = "humidifier_ff", 61.0
    controller._note_switch("humidifier", Decision("humidifier", False, "refill done", tag="humidifier_ff_done"), ctx,
                            now, now + timedelta(seconds=120))
    smp = controller._pending_samples[-1]
    assert smp["role"] == "exchange" and smp["aim"] == 64.0 and abs(smp["swap_min"] - 1.5) < 0.01
    # a sensor-lag later the tent reads 62 %, two points short of the aim: the swap removes more than assumed
    smp["ended"] = utcnow() - timedelta(seconds=LAG_S + 10)
    controller.sensor = SensorSnapshot(24.5, 62.0, 1.0, None, utcnow(), False)
    await controller._learn(ctx)
    assert controller.learned["exchange_rh_drop_per_min"] == 2.5        # one step, capped at 0.5
    assert (await store.get_kv("learned"))["exchange_rh_drop_per_min"] == 2.5
    evs = [e["message"] for e in (await c.get("/api/events", params={"limit": 20})).json()["events"]]
    assert any(m.startswith("Learned: a fresh-air swap lowers humidity about 2.5") for m in evs)
    # a refill that overshoots nudges it back down
    controller._pending_samples.append({**smp, "ended": utcnow() - timedelta(seconds=LAG_S + 10), "on_at": utcnow()})
    controller.sensor = SensorSnapshot(24.5, 65.0, 1.0, None, utcnow(), False)
    await controller._learn(ctx)
    assert controller.learned["exchange_rh_drop_per_min"] == 2.17
