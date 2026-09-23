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

    async def send(self, key: str, message: str, hours: float = 0, title: str = "Grow tent", url: str | None = None,
                   service: str | None = None, everyone: bool = False) -> bool:
        """Send at most once per `hours` for the same key (0 = always).

        service: a specific notify service (a plant owner's phone). everyone: every plant owner's phone plus the
        tent-wide default. Otherwise the tent-wide default from settings.
        """
        now = utcnow()
        last = self._last.get(key)
        if hours and last and now - last < timedelta(hours=hours):
            return False
        try:
            settings = await self.store.get_kv("settings", {}) or {}
            phones = {p["notify_service"] for p in await self.store.plants() if p.get("notify_service")}
            self._cache = (settings, phones)
        except Exception:  # database trouble must not silence an alert: use what worked last time
            settings, phones = getattr(self, "_cache", ({}, set()))
        default = settings.get("notify_service")
        targets = set()
        if service:
            targets.add(service)
        elif everyone:
            targets.update(phones)
            if default:
                targets.add(default)
        elif default:
            targets.add(default)
        if not targets and phones:
            targets.update(phones)  # no tent-wide phone chosen: every plant owner's phone instead of nobody
        if not targets:
            if not self._last.get("_nobody") or now - self._last["_nobody"] > timedelta(hours=24):
                self._last["_nobody"] = now
                log.warning("notification %r not delivered: no phone is linked to any plant", key)
                try:
                    await self.store.add_event("warn", "system", "An alert couldn't be sent to any phone: link each person's "
                                                                 "phone to their plant in Settings → Plants → Notifications.")
                except Exception:
                    pass
            return False
        data = {"url": url} if url else None
        ok = False
        for svc in sorted(targets):
            ok = await self.ha.notify(svc, message, title=title, data=data) or ok
        if ok:
            self._last[key] = now
        return ok
