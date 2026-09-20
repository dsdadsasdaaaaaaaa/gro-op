"""HTTP API tests with an in-process app, a real SQLite store and a stubbed Home Assistant."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

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

    async def ping(self):
        return True

    async def get_states(self):
        out = [{"entity_id": e, "state": s, "attributes": {"friendly_name": e}, "last_updated": self._now, "last_reported": self._now}
               for e, s in self.state.items()]
        for e, (v, u, dc) in self.sensors.items():
            out.append({"entity_id": e, "state": v, "attributes": {"unit_of_measurement": u, "device_class": dc, "friendly_name": e},
                        "last_updated": self._now, "last_reported": self._now})
        return out

    async def turn(self, entity_id, on):
        self.calls.append((entity_id, on))
        self.state[entity_id] = "on" if on else "off"
        return True

    async def notify(self, *a, **k):
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
