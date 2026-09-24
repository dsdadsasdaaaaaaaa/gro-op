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
        self._loaded = False
        self.pending: dict[str, dict] = {}     # key → message that no phone accepted yet (retried every cycle)
        self._failed_service_at: dict[str, datetime] = {}

    async def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            saved = await self.store.get_kv("notify_last", {}) or {}
            for k, v in saved.items():
                try:
                    self._last.setdefault(k, datetime.fromisoformat(v.replace("Z", "+00:00")))
                except (AttributeError, ValueError):
                    pass
        except Exception:
            pass

    async def _save(self) -> None:
        try:
            cutoff = utcnow() - timedelta(days=2)
            await self.store.set_kv("notify_last", {k: v.isoformat() for k, v in self._last.items() if v > cutoff})
        except Exception:
            pass

    async def flush(self) -> None:
        """Retry pushes that no phone accepted (Home Assistant restarting, phone app logged out...)."""
        for key, p in list(self.pending.items()):
            p["tries"] += 1
            ok = await self._deliver(p["targets"], p["message"], p["title"], p["data"])
            if ok:
                self.pending.pop(key, None)
                self._last[key] = utcnow()
                await self._save()
            elif p["tries"] >= 20:   # ~10 min of retries: give up and say so
                self.pending.pop(key, None)
                try:
                    await self.store.add_event("warn", "system", f"A phone alert couldn't be delivered: {p['message'][:120]}")
                except Exception:
                    pass

    async def _deliver(self, targets: set[str], message: str, title: str, data: dict | None) -> bool:
        ok = False
        for svc in sorted(targets):
            sent = await self.ha.notify(svc, message, title=title, data=data)
            ok = sent or ok
            if not sent:
                last = self._failed_service_at.get(svc)
                if not last or utcnow() - last > timedelta(hours=24):
                    self._failed_service_at[svc] = utcnow()
                    try:
                        await self.store.add_event("warn", "system", f"Couldn't send a notification to {svc}. Is the Home "
                                                                     f"Assistant app still installed and signed in on that phone?")
                    except Exception:
                        pass
        return ok

    async def send(self, key: str, message: str, hours: float = 0, title: str = "Grow tent", url: str | None = None,
                   service: str | None = None, everyone: bool = False) -> bool:
        """Send at most once per `hours` for the same key (0 = always).

        service: a specific notify service (a plant owner's phone). everyone: every plant owner's phone plus the
        tent-wide default. Otherwise the tent-wide default from settings.
        """
        await self._load()
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
                    msg = ("An alert couldn't be sent to any phone: link each person's phone to their plant in "
                           "Settings → Plants → Phone for alerts.")
                    await self.store.resolve_alerts("system", "An alert couldn't be sent to any phone")
                    await self.store.add_event("warn", "system", msg)
                except Exception:
                    pass
            return False
        data = {"url": url, "clickAction": url} if url else None   # url: iPhone, clickAction: Android
        ok = await self._deliver(targets, message, title, data)
        if ok:
            self._last[key] = now
            self.pending.pop(key, None)
            await self._save()
        elif hours:   # important, throttled messages get retried until a phone takes them
            self.pending[key] = {"targets": targets, "message": message, "title": title, "data": data, "tries": 0}
        return ok
