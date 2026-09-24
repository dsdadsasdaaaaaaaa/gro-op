"""Minimal async Home Assistant REST client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .devices import SENSOR_DOMAINS, SWITCH_DOMAINS, suggest_role

log = logging.getLogger(__name__)


class HAClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url + "/api",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        self.connected = False
        self.last_error: str | None = None
        self.last_status: int | None = None   # HTTP status of the last failed service call; None = HA didn't answer

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/")
            self.connected = r.status_code == 200
            self.last_error = None if self.connected else f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            self.connected = False
            self.last_error = str(e)
        return self.connected

    async def get_states(self) -> list[dict[str, Any]]:
        try:
            r = await self._client.get("/states")
            r.raise_for_status()
            self.connected = True
            self.last_error = None
            return r.json()
        except httpx.HTTPError as e:
            self.connected = False
            self.last_error = str(e)
            raise

    async def core_config(self) -> dict[str, Any]:
        """Home Assistant's /api/config (location, internal_url...), or {} if unavailable."""
        try:
            r = await self._client.get("/config")
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            return {}

    async def call_service(self, domain: str, service: str, data: dict[str, Any]) -> bool:
        try:
            r = await self._client.post(f"/services/{domain}/{service}", json=data)
            r.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            log.warning("HA service %s.%s failed: %s", domain, service, e)
            self.last_error, self.last_status = str(e), e.response.status_code
            return False
        except httpx.HTTPError as e:
            log.warning("HA service %s.%s failed: %s", domain, service, e)
            self.last_error, self.last_status = str(e), None
            return False

    async def turn(self, entity_id: str, on: bool) -> bool:
        domain = entity_id.split(".", 1)[0]
        # homeassistant.turn_on/off works for switch, light, fan, input_boolean, humidifier...
        return await self.call_service("homeassistant", "turn_on" if on else "turn_off", {"entity_id": entity_id})

    async def notify(self, service: str, message: str, title: str = "Grow tent", data: dict | None = None) -> bool:
        """service is e.g. 'notify.mobile_app_levis_iphone'."""
        if not service:
            return False
        if service.startswith("notify."):
            service = service[len("notify."):]
        payload: dict[str, Any] = {"message": message, "title": title}
        if data:
            payload["data"] = data
        return await self.call_service("notify", service, payload)

    async def camera_image(self, entity_id: str) -> bytes | None:
        """A fresh JPEG from any HA camera entity (Wyze via the bridge, Tapo, ...)."""
        try:
            r = await self._client.get(f"/camera_proxy/{entity_id}", timeout=httpx.Timeout(20.0, connect=5.0))
            if r.status_code != 200 or not r.content:
                self.last_error = f"camera_proxy {r.status_code}"
                return None
            return r.content
        except httpx.HTTPError as e:
            self.last_error = str(e)
            return None

    def camera_stream_request(self, entity_id: str):
        """An open MJPEG stream request (use with `async with client.stream`)."""
        return self._client.stream("GET", f"/camera_proxy_stream/{entity_id}", timeout=httpx.Timeout(None, connect=5.0))

    async def list_notify_services(self) -> list[str]:
        try:
            r = await self._client.get("/services")
            r.raise_for_status()
        except httpx.HTTPError:
            return []
        out = []
        for dom in r.json():
            if dom.get("domain") == "notify":
                for svc in dom.get("services", {}):
                    if svc not in ("persistent_notification", "send_message"):
                        out.append(f"notify.{svc}")
        return sorted(out)

    async def list_candidates(self) -> list[dict[str, Any]]:
        """Entities that could be mapped to a grow role, with a suggested role."""
        states = await self.get_states()
        out = []
        for s in states:
            eid = s["entity_id"]
            domain = eid.split(".", 1)[0]
            if domain not in SWITCH_DOMAINS | SENSOR_DOMAINS:
                continue
            attrs = s.get("attributes", {})
            unit = attrs.get("unit_of_measurement")
            dc = attrs.get("device_class")
            if domain == "sensor" and unit is None and dc is None:
                continue  # text sensors are never climate sensors
            out.append({
                "entity_id": eid,
                "name": attrs.get("friendly_name") or eid,
                "domain": domain,
                "state": s.get("state"),
                "unit": unit,
                "device_class": dc,
                "suggested_role": suggest_role(eid, attrs.get("friendly_name"), dc, unit),
            })
        out.sort(key=lambda e: (e["suggested_role"] is None, e["domain"], e["name"].lower()))
        return out
