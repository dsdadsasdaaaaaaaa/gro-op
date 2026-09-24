"""Follow-up jobs the app adds by itself, so nobody has to remember them. Shared by the API (a ticked task or a
log entry) and the advisor (a planting it recorded from a conversation)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

DOME_OFF_DETAIL = ("Lift the clear cup or bag off once the first true leaves (the first jagged pair, not the round starter "
                   "leaves) are open. Leaving it on longer invites mould at the soil line. No dome on this cup? Just tick this off.")


async def dome_reminder(store, controller, plant_id: Optional[int]) -> Optional[int]:
    """'Take the dome off …' four days out, once per plant (never a second copy while one is open)."""
    plant = await store.get_plant(plant_id) if plant_id else None
    title = f"Take the dome off {plant['name'] if plant else 'the seedlings'}"
    if title in {x["title"] for x in await store.tasks("open")}:
        return None
    tz = controller.tz(await controller.settings())
    due = (datetime.now(tz).date() + timedelta(days=4)).isoformat()
    t = await store.add_task(title, DOME_OFF_DETAIL, due, "normal", "system", plant_id)
    return t["id"]


async def after_log(store, controller, kind: str, plant_id: Optional[int]) -> list[int]:
    """What a planting or a transplant sets in motion. Returns the ids of the tasks it added."""
    added: list[int] = []
    if kind == "planted" and plant_id:
        # every seedling starts under a dome here, so every planting gets the reminder to take it off
        tid = await dome_reminder(store, controller, plant_id)
        if tid:
            added.append(tid)
    if kind == "transplant":
        profile = await controller.profile()
        if profile.get("stage") == "seedling":
            title = "Switch the stage to Veg"
            if title not in {t["title"] for t in await store.tasks("open")}:
                t = await store.add_task(title, "The plants are in their big pots. Settings → Change stage → Veg, so the tent "
                                                "switches to veg temperature, humidity and air exchange. Plug the two small lights "
                                                "back in and turn the big one up first.", None, "high", "system", None)
                added.append(t["id"])
    return added
