"""A fake Home Assistant with a simulated tent, for trying Grow Brain without touching real plugs.

    python -m grow_brain.mock_ha            # serves on http://127.0.0.1:8123
    HA_URL=http://127.0.0.1:8123 HA_TOKEN=x GROW_API_KEY=test DATA_DIR=./data python -m grow_brain.main

The physics are crude but directionally right: the light heats the tent, the exhaust cools and dries it,
the humidifier adds moisture, plants transpire, and everything drifts toward the room.
"""

from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request

ROOM_T, ROOM_RH = 21.0, 45.0

state = {
    "switch.grow_light": "off",
    "switch.grow_exhaust_fan": "off",
    "switch.grow_circulation_fan": "off",
    "switch.grow_humidifier": "off",
    "switch.grow_heater": "off",
    "switch.grow_dehumidifier": "off",
}
tent = {"t": 23.0, "rh": 55.0}
names = {
    "switch.grow_light": "Grow Light",
    "switch.grow_exhaust_fan": "Grow Exhaust Fan",
    "switch.grow_circulation_fan": "Grow Circulation Fan",
    "switch.grow_humidifier": "Grow Humidifier",
    "switch.grow_heater": "Grow Heater",
    "switch.grow_dehumidifier": "Grow Dehumidifier",
}
last_updated = {k: datetime.now(timezone.utc) for k in state}
sensor_updated = datetime.now(timezone.utc)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(physics())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@app.get("/api/")
async def root():
    return {"message": "API running."}


@app.get("/api/states")
async def states():
    now = datetime.now(timezone.utc)
    out = []
    for eid, st in state.items():
        out.append({"entity_id": eid, "state": st, "attributes": {"friendly_name": names[eid]},
                    "last_updated": _iso(last_updated[eid]), "last_reported": _iso(now)})
    out.append({"entity_id": "sensor.grow_tent_temperature", "state": f"{tent['t']:.1f}",
                "attributes": {"friendly_name": "Grow Tent Temperature", "unit_of_measurement": "°C", "device_class": "temperature"},
                "last_updated": _iso(sensor_updated), "last_reported": _iso(sensor_updated)})
    out.append({"entity_id": "sensor.grow_tent_humidity", "state": f"{tent['rh']:.1f}",
                "attributes": {"friendly_name": "Grow Tent Humidity", "unit_of_measurement": "%", "device_class": "humidity"},
                "last_updated": _iso(sensor_updated), "last_reported": _iso(sensor_updated)})
    out.append({"entity_id": "sensor.grow_light_power", "state": "0",
                "attributes": {"friendly_name": "Grow Light Power", "unit_of_measurement": "W", "device_class": "power"},
                "last_updated": _iso(now), "last_reported": _iso(now)})
    return out


@app.get("/api/services")
async def services():
    return [{"domain": "notify", "services": {"mobile_app_test_iphone": {}, "persistent_notification": {}}},
            {"domain": "homeassistant", "services": {"turn_on": {}, "turn_off": {}}}]


@app.post("/api/services/{domain}/{service}")
async def call(domain: str, service: str, request: Request):
    body = await request.json()
    if domain == "notify":
        print(f"[notify.{service}] {body.get('title')}: {body.get('message')}", flush=True)
        return []
    eid = body.get("entity_id")
    if eid in state and service in ("turn_on", "turn_off"):
        new = "on" if service == "turn_on" else "off"
        if state[eid] != new:
            state[eid] = new
            last_updated[eid] = datetime.now(timezone.utc)
            print(f"[{eid}] -> {new}", flush=True)
    return []


async def physics():
    global sensor_updated
    while True:
        await asyncio.sleep(2)
        dt = 2 / 60  # minutes
        t, rh = tent["t"], tent["rh"]
        # heat sources / sinks (°C per minute)
        dT = 0.0
        dT += 0.25 if state["switch.grow_light"] == "on" else 0.0
        dT += 0.35 if state["switch.grow_heater"] == "on" else 0.0
        dT += 0.05 if state["switch.grow_dehumidifier"] == "on" else 0.0
        dT -= 0.5 * (t - ROOM_T) / 10 if state["switch.grow_exhaust_fan"] == "on" else 0.0
        dT -= 0.06 * (t - ROOM_T) / 10  # leakage
        # humidity (% per minute)
        dH = 0.0
        dH += 0.9 if state["switch.grow_humidifier"] == "on" else 0.0
        dH -= 1.2 if state["switch.grow_dehumidifier"] == "on" else 0.0
        dH += 0.15  # transpiration
        dH -= 0.6 * (rh - ROOM_RH) / 10 if state["switch.grow_exhaust_fan"] == "on" else 0.0
        dH -= 0.08 * (rh - ROOM_RH) / 10
        dH -= 0.4 * dT  # warmer air = lower RH
        tent["t"] = round(t + dT * dt + random.uniform(-0.02, 0.02), 2)
        tent["rh"] = round(max(10, min(99, rh + dH * dt + random.uniform(-0.1, 0.1))), 2)
        sensor_updated = datetime.now(timezone.utc)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8123, log_level="warning")
