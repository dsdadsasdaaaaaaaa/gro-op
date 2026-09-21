"""Tent camera via Home Assistant (any `camera.*` entity: Wyze through Docker Wyze Bridge, Tapo, ...).

The grow brain never talks to the bridge itself; it uses HA's camera proxy, which works for every
camera integration and through the Supervisor token. Features:
  * fresh snapshot / MJPEG stream passthrough for the apps
  * a timelapse: one frame every `camera_capture_minutes` while the tent is running (kept 14 days)
  * the advisor gets the latest lights-on frame with the daily brief and on demand ("look now")
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .store import Store, iso, parse_iso, utcnow

log = logging.getLogger(__name__)

_PREFERRED = ("wyze", "tent", "grow")


class CameraService:
    def __init__(self, store: Store, ha, controller, frames_dir: Path):
        self.store = store
        self.ha = ha
        self.controller = controller
        self.frames_dir = frames_dir
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._cache: tuple[datetime, bytes] | None = None
        self._task: Optional[asyncio.Task] = None
        self.last_error: Optional[str] = None

    # ---- selection ----
    def candidates(self) -> list[dict]:
        out = []
        for eid, st in self.controller.states.items():
            if not eid.startswith("camera."):
                continue
            attrs = st.get("attributes", {})
            out.append({"entity_id": eid, "name": attrs.get("friendly_name") or eid, "state": st.get("state"),
                        "brand": attrs.get("brand"), "model": attrs.get("model_name")})
        out.sort(key=lambda c: (not any(w in (c["name"] + c["entity_id"]).lower() for w in _PREFERRED), c["name"].lower()))
        return out

    async def entity_id(self) -> Optional[str]:
        settings = await self.controller.settings()
        eid = settings.get("camera_entity")
        if eid == "":
            return None  # explicitly off
        if eid and eid in self.controller.states:
            return eid
        cands = [c for c in self.candidates() if c["state"] not in ("unavailable", "unknown", None)]
        auto = next((c["entity_id"] for c in cands if any(w in (c["name"] + c["entity_id"]).lower() for w in _PREFERRED)), None)
        return auto

    async def info(self) -> Optional[dict]:
        eid = await self.entity_id()
        if not eid:
            return None
        st = self.controller.states.get(eid, {})
        latest = await self.store.latest_frame()
        return {
            "entity_id": eid,
            "name": st.get("attributes", {}).get("friendly_name") or eid,
            "available": st.get("state") not in (None, "unavailable", "unknown"),
            "snapshot_url": "/api/camera/snapshot",
            "stream_url": "/api/camera/stream",
            "last_frame_at": latest["t"] if latest else None,
            "frame_count": await self.store.frame_count(),
            "error": self.last_error,
        }

    # ---- snapshots ----
    async def snapshot(self, max_age_s: float = 2.0) -> Optional[bytes]:
        eid = await self.entity_id()
        if not eid:
            return None
        now = utcnow()
        if self._cache and (now - self._cache[0]).total_seconds() < max_age_s:
            return self._cache[1]
        data = await self.ha.camera_image(eid)
        if data:
            self._cache = (now, data)
            self.last_error = None
        else:
            self.last_error = self.ha.last_error or "no image from Home Assistant"
        return data

    async def capture_frame(self) -> Optional[dict]:
        data = await self.snapshot(max_age_s=0)
        if not data:
            return None
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as e:
            self.last_error = f"bad image: {e}"
            return None
        im.thumbnail((1280, 1280))
        ts = utcnow()
        path = self.frames_dir / f"{ts.strftime('%Y%m%d_%H%M%S')}.jpg"
        im.save(path, "JPEG", quality=80)
        lights_on = self.controller.sensor is not None and bool(getattr(self.controller, "_last_lights_on", None))
        fid = await self.store.add_frame(str(path), lights_on)
        return {"id": fid, "t": iso(ts), "path": str(path), "lights_on": lights_on}

    async def latest_frame_for_advisor(self, max_age_h: float = 6.0) -> Optional[tuple[bytes, str]]:
        """Latest frame (prefer lights-on) recent enough to be worth showing the advisor."""
        for prefer_lit in (True, False):
            fr = await self.store.latest_frame(lights_on=True if prefer_lit else None)
            if fr and parse_iso(fr["t"]) and utcnow() - parse_iso(fr["t"]) < timedelta(hours=max_age_h):
                p = Path(fr["path"])
                if p.exists():
                    return p.read_bytes(), fr["t"]
        # nothing stored: try a live one
        data = await self.snapshot(max_age_s=0)
        return (data, iso(utcnow())) if data else None

    # ---- loop ----
    async def run(self) -> None:
        await asyncio.sleep(20)
        while True:
            try:
                settings = await self.controller.settings()
                minutes = max(5, int(settings.get("camera_capture_minutes", 30)))
                if await self.entity_id():
                    await self.capture_frame()
                    await self.store.prune_frames(keep_days=14, frames_dir=self.frames_dir)
            except Exception:
                log.exception("camera capture failed")
                minutes = 30
            await asyncio.sleep(minutes * 60)

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
