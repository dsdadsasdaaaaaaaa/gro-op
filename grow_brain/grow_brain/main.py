"""Process entry point: FastAPI app + control loop + daily-brief scheduler."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import __version__
from .advisor import Advisor
from .api import router
from .config import load_boot_config
from .controller import Controller
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
            hh, mm = (int(x) for x in (settings.get("brief_time") or "08:00").split(":"))
            last = await st.store.get_kv("last_brief_date")
            if st.advisor.enabled and (now.hour, now.minute) >= (hh, mm) and last != now.date().isoformat():
                dmap = await st.store.get_device_map()
                if dmap.get("temperature_sensor"):
                    await st.store.set_kv("last_brief_date", now.date().isoformat())
                    log.info("Running daily brief")
                    try:
                        await st.advisor.daily_brief()
                    except Exception as e:
                        log.warning("daily brief failed: %s", e)
                        await st.store.add_event("warn", "advisor", f"Daily brief failed: {e}")
        except Exception:
            log.exception("brief scheduler error")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    boot = load_boot_config()
    logging.basicConfig(level=getattr(logging, boot.log_level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
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
    advisor = Advisor(store, controller, boot.anthropic_api_key, boot.model, notifier, photo_dir)

    app.state.boot = boot
    app.state.store = store
    app.state.controller = controller
    app.state.advisor = advisor
    app.state.photo_dir = photo_dir

    if await ha.ping():
        log.info("Home Assistant reachable at %s", boot.ha_url)
    else:
        log.warning("Home Assistant NOT reachable at %s: %s (will keep retrying)", boot.ha_url, ha.last_error)

    controller.start()
    sched = asyncio.create_task(brief_scheduler(app))
    try:
        yield
    finally:
        sched.cancel()
        await controller.stop()
        await ha.close()
        await store.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Grow Brain", version=__version__, lifespan=lifespan)
    app.include_router(router)

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
