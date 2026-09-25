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


async def sprouted(store, controller, plant_id: int) -> None:
    """A seedling came up: its dome comes off about five days later (once the first true leaves open), so the
    reminder is dated from today instead of from the planting."""
    plant = await store.get_plant(plant_id)
    if not plant:
        return
    tz = controller.tz(await controller.settings())
    due = (datetime.now(tz).date() + timedelta(days=5)).isoformat()
    title = f"Take the dome off {plant['name']}"
    for t in await store.tasks("open"):
        if t["title"] == title:
            await store.set_task_due(t["id"], due)


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


# The max-yield program: jobs each stage starts, as (days after the stage change, one per plant?, title, detail).
STAGE_JOBS: dict[str, list[tuple[int, bool, str, str]]] = {
    "veg": [
        (12, True, "Top above the 5th node",
         "When the plant has 5–6 nodes (pairs of leaves along the main stem), cut the main stem just above the 5th node "
         "with clean scissors. Two main tops grow from there. Optional for even more tops: once each new top has 3 nodes, "
         "top those too. Skip it for a day or two if the plant looks stressed."),
        (16, True, "Start low-stress training",
         "About two days after topping: gently bend the new tops outward and tie them to the pot rim with soft plant ties. "
         "Adjust the ties every 2–3 days so the plant grows flat and wide instead of tall. Bend, never snap."),
        (18, False, "Put up the trellis net",
         "Stretch a trellis net across the tent about 20–25 cm above the pot rims. As tops reach it, tuck them under and "
         "outward to the next square so every top ends up at the same height under the light."),
        (28, False, "Is the net 70 % full? Time to flip",
         "Flip to flower when the net is about 70 % full (the plants roughly double in the first 3 weeks of flower): "
         "Settings → Change stage → Flower, and the light switches to 12 hours by itself. Not full yet? Tick this off and "
         "check again in a few days."),
    ],
    "flower": [
        (2, True, "Lollipop the lower third",
         "Remove the small branches and leaves on the bottom third of the plant, below the net: they never get enough light "
         "to make real buds and only steal energy from the tops."),
        (21, True, "Day-21 defoliation",
         "Remove the big fan leaves that shade bud sites, and anything new growing below the net. Take at most 20–30 % of "
         "the leaves, spread evenly."),
        (49, True, "Start checking trichomes",
         "Every 2–3 days, look at the trichomes on the buds (not the small sugar leaves) with the loupe: clear = wait, "
         "mostly cloudy = peak, 10–15 % amber = harvest window. Photos help the advisor judge it."),
    ],
    "flush": [
        (0, False, "Plain water only until harvest",
         "No more nutrients: water with plain water to a little runoff until harvest. Yellowing leaves now are normal."),
    ],
    "drying": [
        (7, False, "Check if the buds are dry",
         "Bend a small stem: if it snaps instead of bending, trim the buds and put them in jars with a 62 % humidity pack. "
         "If it still bends, check again every day or two."),
    ],
}


async def stage_started(store, controller, stage: str) -> list[int]:
    """Lay out the stage's jobs with their dates, one per plant where each plant needs it done."""
    jobs = STAGE_JOBS.get(stage) or []
    if not jobs:
        return []
    tz = controller.tz(await controller.settings())
    today = datetime.now(tz).date()
    plants = await store.plants()
    open_titles = {t["title"] for t in await store.tasks("open")}
    added: list[int] = []
    for offset, per_plant, title, detail in jobs:
        due = (today + timedelta(days=offset)).isoformat()
        for plant in (plants if per_plant and plants else [None]):
            full = f"{title}: {plant['name']}" if plant else title
            if full in open_titles:
                continue
            t = await store.add_task(full, detail, due, "normal", "system", plant["id"] if plant else None)
            open_titles.add(full)
            added.append(t["id"])
    return added
