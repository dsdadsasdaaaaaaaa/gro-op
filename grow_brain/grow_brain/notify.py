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
        self._cleared: set[str] = set()        # phones whose "couldn't send" warning is known to be closed
        self._ha_trouble = False               # the last failure was Home Assistant itself, not a phone

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
        if self.pending and not getattr(self.ha, "connected", True):
            return    # Home Assistant is the way out to the phones: wait for it instead of burning the retries
        for key, p in list(self.pending.items()):
            if utcnow() - p.get("at", utcnow()) > timedelta(hours=12):
                self.pending.pop(key, None)   # too old to still matter
                continue
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
        self._ha_trouble = False
        for svc in sorted(targets):
            sent = await self.ha.notify(svc, message, title=title, data=data)
            ok = sent or ok
            if sent:
                if svc not in self._cleared or svc in self._failed_service_at:
                    # it reaches that phone again: an earlier "couldn't send" warning is over
                    self._failed_service_at.pop(svc, None)
                    self._cleared.add(svc)
                    try:
                        await self.store.resolve_alerts("system", f"Couldn't send a notification to {svc}")
                    except Exception:
                        pass
                continue
            status = getattr(self.ha, "last_status", None)
            if status is None or status >= 500 or status in (401, 403):
                # Home Assistant itself didn't answer (restarting, down, token): not the phone's fault
                self._ha_trouble = True
                continue
            if not sent:
                self._cleared.discard(svc)
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
        elif hours or self._ha_trouble:   # important messages, and anything Home Assistant couldn't pass on, get retried
            self.pending[key] = {"targets": targets, "message": message, "title": title, "data": data, "tries": 0, "at": now}
        return ok
