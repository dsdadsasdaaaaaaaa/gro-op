"""Process entry point: FastAPI app + control loop + daily-brief scheduler."""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import uvicorn
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .advisor import Advisor
from .api import router
from .camera import CameraService
from .config import load_boot_config
from .controller import Controller, parse_hhmm
from .ha import HAClient
from .notify import Notifier
from .store import Store

log = logging.getLogger("grow_brain")


async def brief_scheduler(app: FastAPI) -> None:
    """Runs the daily brief once per local day at settings.brief_time."""
    st = app.state
    while True:
        try:
            settings = await st.controller.settings()
            tz = st.controller.tz(settings)
            now = datetime.now(tz)
            hh, mm = parse_hhmm(settings.get("brief_time"), "08:00")
            last = await st.store.get_kv("last_brief_date")
            today = now.date().isoformat()
            if st.advisor.enabled and (now.hour, now.minute) >= (hh, mm) and last != today and not await st.controller.standby():
                dmap = await st.store.get_device_map()
                att = await st.store.get_kv("brief_attempts", {}) or {}
                tries, last_try = (att.get("n", 0), att.get("at")) if att.get("date") == today else (0, None)
                due_retry = not last_try or (datetime.now(timezone.utc) - datetime.fromisoformat(last_try)).total_seconds() >= 20 * 60
                if dmap.get("temperature_sensor") and tries < 3 and due_retry:
                    await st.store.set_kv("brief_attempts", {"date": today, "n": tries + 1, "at": datetime.now(timezone.utc).isoformat()})
                    log.info("Running daily brief (attempt %d)", tries + 1)
                    try:
                        await st.advisor.daily_brief()
                        await st.store.set_kv("last_brief_date", today)
                    except Exception as e:
                        log.warning("daily brief failed: %s", e)
                        if tries + 1 >= 3:
                            await st.store.set_kv("last_brief_date", today)
                            await st.store.add_event("warn", "advisor", f"The morning brief couldn't be written today ({e}).")
                            await st.notifier.send("brief_failed", "The morning brief couldn't be written today. The tent is "
                                                   "still being controlled; ask the advisor in the app if you need anything.",
                                                   hours=20, everyone=True)
        except Exception:
            log.exception("brief scheduler error")
        for tick in (_camera_check_tick, _nudge_tick, _update_check_tick):
            try:
                await tick(st)
            except Exception:
                log.exception("scheduler tick %s failed", tick.__name__)
        await asyncio.sleep(60)


REPO_CONFIG_URL = "https://raw.githubusercontent.com/dsdadsasdaaaaaaaa/gro-op/main/grow_brain/config.yaml"


def _vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v))


class _RedactKey(logging.Filter):
    """Access-log lines include the query string; hide ?api_key=... there."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.args and isinstance(record.args, tuple):
                record.args = tuple(re.sub(r"(api_key=)[^&\s\"]+", r"\1***", a) if isinstance(a, str) else a for a in record.args)
        except Exception:
            pass
        return True


async def _ci_passed() -> bool:
    """True unless GitHub says the latest build of main failed (no answer counts as passed)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://api.github.com/repos/dsdadsasdaaaaaaaa/gro-op/commits/main/check-runs",
                                 headers={"Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                return True
            runs = r.json().get("check_runs", [])
        return not any(run.get("conclusion") in ("failure", "cancelled", "timed_out") for run in runs) and \
            all(run.get("status") == "completed" for run in runs)
    except Exception:
        return True


async def _update_check_tick(st) -> None:
    """Every 6 hours: is a newer add-on version published? A failed build in Home Assistant is easy to miss,
    so the timeline says so until the running version catches up."""
    now = datetime.now(timezone.utc)
    last = await st.store.get_kv("update_check_at")
    fresh_install = await st.store.get_kv("update_check_version") != __version__   # just updated: check right away
    if last and not fresh_install and (now - datetime.fromisoformat(last)).total_seconds() < 6 * 3600:
        return
    await st.store.set_kv("update_check_at", now.isoformat())
    await st.store.set_kv("update_check_version", __version__)
    # notices and advisor tasks about versions we're already running are finished
    for a in await st.store.events(limit=200, min_level="warn", hours=24 * 30):
        m = re.match(r"Grow Brain ([\d.]+) is available", a.get("message", ""))
        if m and _vtuple(m.group(1)) <= _vtuple(__version__):
            await st.store.resolve_alerts("system", f"Grow Brain {m.group(1)} is available")
    for t in await st.store.tasks("open"):
        m = re.search(r"update grow brain(?: to)? ?v?([\d.]+)?", t["title"].lower())
        if m and (not m.group(1) or _vtuple(m.group(1)) <= _vtuple(__version__)):
            await st.store.set_task_status(t["id"], "done")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(REPO_CONFIG_URL)
            r.raise_for_status()
        mm = re.search(r'^version:\s*"?([\d.]+)"?', r.text, re.M)
        latest = mm.group(1) if mm else None
    except Exception as e:  # offline or GitHub hiccup: try again next time
        log.debug("update check skipped: %s", e)
        return
    if not latest:
        return
    if _vtuple(latest) > _vtuple(__version__):
        if not await _ci_passed():
            return          # a broken build would fail to install: wait for a good one
        if await st.store.get_kv("update_notified") != latest:
            await st.store.set_kv("update_notified", latest)
            settings = await st.controller.settings()
            admin = settings.get("admin_notify_service") or next(
                (p.get("notify_service") for p in await st.store.plants() if p.get("notify_service")), None)
            await st.notifier.send("update", f"Grow Brain {latest} is ready. Home Assistant → Settings → Add-ons → Grow Brain → Update.",
                                   hours=24, service=admin, everyone=admin is None)
            await st.store.add_event("warn", "system",
                                     f"Grow Brain {latest} is available (running {__version__}). Home Assistant → Settings → "
                                     f"Add-ons → Grow Brain → Update.")
    else:
        await st.store.resolve_alerts("system", "Grow Brain ")


async def _camera_check_tick(st) -> None:
    """One hour after lights-on, once per local day, while the tent is running."""
    if not st.advisor.enabled or not await st.camera.entity_id() or await st.controller.standby():
        return
    settings = await st.controller.settings()
    tz = st.controller.tz(settings)
    now = datetime.now(tz)
    targets, _, _ = await st.controller.effective_targets()
    if targets.light_hours <= 0:
        return
    hh, mm = parse_hhmm(targets.light_on_time)
    minutes_since_on = ((now.hour * 60 + now.minute) - (hh * 60 + mm)) % (24 * 60)
    if not (60 <= minutes_since_on < 120):
        return
    today = now.date().isoformat()
    if await st.store.get_kv("last_camera_check_date") == today:
        return
    att = await st.store.get_kv("camera_check_attempts", {}) or {}
    tries = att.get("n", 0) if att.get("date") == today else 0
    if tries >= 3 or (att.get("date") == today and att.get("minute", -99) > minutes_since_on - 15):
        return
    await st.store.set_kv("camera_check_attempts", {"date": today, "n": tries + 1, "minute": minutes_since_on})
    log.info("Running daily camera check (attempt %d)", tries + 1)
    try:
        await st.advisor.camera_check()
        await st.store.set_kv("last_camera_check_date", today)
    except Exception as e:
        log.warning("camera check failed: %s", e)
        if tries + 1 >= 3:
            await st.store.set_kv("last_camera_check_date", today)
            await st.store.add_event("info", "advisor", f"The daily camera check couldn't run today ({e}).")


async def _nudge_tick(st) -> None:
    """Remind the plant's owner about photo requests that have sat open for two days (at most once a day)."""
    last = await st.store.get_kv("last_nudge_hour")
    hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    if last == hour_key:
        return
    await st.store.set_kv("last_nudge_hour", hour_key)
    await st.store.expire_photo_requests(days=7)
    plants = {p["id"]: p for p in await st.store.plants()}
    for pr in await st.store.photo_requests_to_nudge(older_than_hours=48, nudge_gap_hours=24):
        plant = plants.get(pr.get("plant_id"))
        who = f" for {plant['name']}" if plant else ""
        svc = plant.get("notify_service") if plant else None
        url = f"growop://photos?plant={plant['id']}" if plant else "growop://photos"
        await st.notifier.send(f"nudge:{pr['id']}", f"Still waiting for a photo{who}: {pr['title']}", title="Photo request",
                               url=url, service=svc, everyone=svc is None)
        await st.store.mark_nudged(pr["id"])
    await _stage_backstop(st)


async def _stage_backstop(st) -> None:
    """Three and a half weeks as seedlings: remind them to transplant and switch the stage, once."""
    profile = await st.controller.profile()
    if profile.get("stage") != "seedling" or await st.controller.standby():
        return
    _, day_in_stage, _ = await st.controller.effective_targets(profile)
    if day_in_stage < 24 or await st.store.get_kv("veg_backstop_sent"):
        return
    await st.store.set_kv("veg_backstop_sent", True)
    open_titles = {t["title"] for t in await st.store.tasks("open")}
    if "Switch the stage to Veg" not in open_titles:
        await st.store.add_task("Switch the stage to Veg", "The seedlings are over three weeks old. Once they're in their 11 L "
                                "pots: plug the two small lights back in, turn the big one up, then Settings → Change stage → Veg.",
                                None, "normal", "system", None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    boot = load_boot_config()
    logging.basicConfig(level=getattr(logging, boot.log_level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").addFilter(_RedactKey())
    log.info("Grow Brain %s starting (add-on=%s, HA=%s, model=%s, data=%s)", __version__, boot.in_addon, boot.ha_url, boot.model, boot.data_dir)
    if not boot.anthropic_api_key:
        log.warning("No Anthropic API key set: the advisor (briefs, photo analysis, chat, log advice) is OFF.")

    store = Store(boot.data_dir / "grow_brain.sqlite")
    await store.open()
    ha = HAClient(boot.ha_url, boot.ha_token)
    notifier = Notifier(ha, store)
    controller = Controller(store, ha, boot.timezone, notifier)
    photo_dir = boot.data_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    camera = CameraService(store, ha, controller, boot.data_dir / "camera")
    advisor = Advisor(store, controller, boot.anthropic_api_key, boot.model, notifier, photo_dir, camera)

    # Upgrading from a single-plant install: turn the old grow profile into plant #1.
    if not await store.plants(include_archived=True):
        prof = await store.get_kv("grow_profile", None) or {}
        settings = await store.get_kv("settings", {}) or {}
        first = await store.add_plant(
            name="My plant", owner="", strain=prof.get("strain", "Liberty Haze"), breeder=prof.get("breeder", "Barney's Farm"),
            seed_type=prof.get("seed_type", "feminized photoperiod"), medium=prof.get("medium", "soil"),
            pot_size_l=prof.get("pot_size_l", 11.0), start_date=prof.get("start_date"), notes=prof.get("notes", ""),
            notify_service=settings.get("notify_service"))
        await store.assign_orphans_to_plant(first["id"])
        log.info("Created plant #%s from the existing grow profile", first["id"])

    app.state.boot = boot
    app.state.store = store
    app.state.controller = controller
    app.state.advisor = advisor
    app.state.photo_dir = photo_dir
    app.state.camera = camera
    app.state.ha = ha

    if await ha.ping():
        log.info("Home Assistant reachable at %s", boot.ha_url)
    else:
        log.warning("Home Assistant NOT reachable at %s: %s (will keep retrying)", boot.ha_url, ha.last_error)

    controller.start()
    camera.start()
    sched = asyncio.create_task(brief_scheduler(app))
    try:
        yield
    finally:
        sched.cancel()
        await camera.stop()
        await controller.stop()
        await ha.close()
        await store.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Grow Brain", version=__version__, lifespan=lifespan)
    app.include_router(router)

    web = Path(__file__).parent / "web"
    if (web / "index.html").exists():
        if (web / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(web / "assets")), name="assets")

        @app.middleware("http")
        async def _no_cache_assets(request, call_next):
            response = await call_next(request)
            if request.url.path.startswith("/assets/") or request.url.path == "/":
                response.headers["Cache-Control"] = "no-cache"
            return response

        @app.get("/", include_in_schema=False)
        async def dashboard():
            return FileResponse(web / "index.html", headers={"Cache-Control": "no-cache"})

    else:
      @app.get("/", response_class=HTMLResponse, include_in_schema=False)
      async def root():
        # Fallback when the dashboard files are missing. The real UI is the GrowOp apps.
        st = app.state
        ok = st.controller.ha_ok
        return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>Grow Brain</title><style>body{{font-family:-apple-system,system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;line-height:1.5}}
code{{background:#eee;padding:.1rem .3rem;border-radius:.2rem}}</style></head><body>
<h1>🌱 Grow Brain {__version__}</h1>
<p>Status: <b>{'running, Home Assistant connected' if ok else 'running, waiting for Home Assistant'}</b>.
Advisor: <b>{'on' if st.advisor.enabled else 'off (no Anthropic key)'}</b>.</p>
<p>Everything is controlled from the <b>GrowOp</b> iPhone app. On the same Wi‑Fi use
<code>http://homeassistant.local:8099</code>; from anywhere, choose <i>Connect through Home Assistant</i>
in the app and paste your Home Assistant URL plus a long-lived access token.</p>
</body></html>"""

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": f"Server error: {exc}"}, status_code=500)

    return app


app = create_app()


def main() -> None:
    boot = load_boot_config()
    uvicorn.run("grow_brain.main:app", host="0.0.0.0", port=boot.port, log_level="info")


if __name__ == "__main__":
    main()
