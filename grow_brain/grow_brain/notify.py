"""Push notifications through Home Assistant's notify services (e.g. the HA companion app)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .ha import HAClient
from .store import Store, utcnow

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, ha: HAClient, store: Store):
        self.ha = ha
        self.store = store
        self._last: dict[str, datetime] = {}

    async def send(self, key: str, message: str, hours: float = 0, title: str = "Grow tent", url: str | None = None) -> bool:
        """Send at most once per `hours` for the same key (0 = always)."""
        now = utcnow()
        last = self._last.get(key)
        if hours and last and now - last < timedelta(hours=hours):
            return False
        settings = await self.store.get_kv("settings", {}) or {}
        service = settings.get("notify_service")
        if not service:
            return False
        data = {"url": url} if url else None
        ok = await self.ha.notify(service, message, title=title, data=data)
        if ok:
            self._last[key] = now
        return ok
