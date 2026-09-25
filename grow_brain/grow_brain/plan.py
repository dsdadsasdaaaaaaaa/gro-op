"""The grow plan: one source of truth for the phases of this grow.

Used by GET /api/plan (the roadmap in the app) and pasted into the advisor's system prompt so the
advice it gives matches what the app shows. Written for a first-time grower: one Liberty Haze in soil,
a small cup first, then an 11 L pot, under an LED in a tent.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, timedelta


@dataclass
class Phase:
    key: str
    title: str
    subtitle: str
    start_day: int
    end_day: int
    what: list[str]
    watch_for: list[str]
    environment: str


PHASES: list[Phase] = [
    Phase("germination", "Germination", "Paper towel until the taproot shows", 0, 3,
          ["Keep the paper towel damp (not dripping) inside a zip bag or between two plates, in the dark at 22–26 °C.",
           "Look once a day, no poking. Liberty Haze usually cracks in 24–72 h.",
           "Meanwhile fill a small cup (0.4–0.5 L, 4–5 holes in the bottom) with light potting soil and moisten it with plain room-temperature tap water (no pH kit needed until feeding starts). Stand it in a saucer."],
          ["Taproot 5–10 mm → plant it the same day, root down, 1 cm deep, cover lightly, mist the surface.",
           "No crack after 5 days → soak 12 h again in a shot glass, then back in the towel."],
          "22–26 °C, dark, damp"),
    Phase("seedling", "Seedling in a cup", "A small cup so the roots fill it fast and you can't overwater", 3, 21,
          ["Plant in the small cup, not the big pot: roots clump into a tight ball and watering stays easy.",
           "Water only when the cup feels light (lift it right after watering and again when dry to learn the difference): about 30–60 ml in a ring around the stem in week 1, up to 100–150 ml by week 3. Overwatering is the #1 beginner killer.",
           "No nutrients yet: fresh soil feeds it for 2–3 weeks.",
           "Light: only the big light, hung high (60–70 cm above the cups) with its dimmer at about 75 % (the light plug shows about 175 W); the two small lights stay unplugged until the transplant. Hanging it higher doesn't cool the tent, dimming does. From week 2, lower it about 5 cm every few days.",
           "Optional: a clear cup with two small air holes over each seedling for the first 3–5 days to hold humidity; take it off once the first true leaves (the first jagged pair, not the round starter leaves) open."],
          ["Stretching, thin, leaning stem → not enough light: lower the light 5 cm or turn the dimmer up a little.",
           "Drooping with wet soil → overwatered; let it dry out.",
           "Roots showing at the drainage holes or 4–5 sets of leaves (about 3 weeks) → transplant to the 11 L pot.",
           "Before the transplant, have ready: two 11 L pots with holes, about 25 L of light potting soil, and two saucers."],
          "22–26 °C day, 65–75 % RH (VPD 0.4–0.8), 18 h light"),
    Phase("veg", "Veg in the final pot", "Build the frame that will carry the buds", 21, 49,
          ["Transplant: water the cup first, fill the 11 L pot, drop the root ball in, water it in gently (about 1 L). Then plug the two small lights back in and set Settings → Change stage → Veg: the app lays out the training jobs with their dates.",
           "Light: all three lights. The advisor says when to turn the big one up (about 250–350 W at the light plug for the first two weeks, then 350–440 W) and checks the result on the plug.",
           "Water to 10–20 % runoff, then let the pot get light before watering again (lift it: heavy = wait). About 1 L at first, 2–3 L later; empty the saucer after 15 min.",
           "Start feeding 2–3 weeks after transplant at ¼–½ strength, the feed brought to pH 6.3–6.5 with the Bluelab pen. More is not better.",
           "Top above the 5th node once the plant has 5–6 nodes (about 10–14 days after the transplant): two main tops. Topping those again later gives 4 tops per plant.",
           "Low-stress training from 2 days after topping: tie the tops outward to the pot rim and adjust the ties every 2–3 days, so the plant grows flat and wide.",
           "Trellis net 20–25 cm above the pot rims: tuck each top under and outward as it reaches the net so the whole canopy ends up level under the light.",
           "Take a photo when asked: the advisor watches for pale leaves, tip burn and stretch."],
          ["Lower leaves going pale yellow → start or increase feed.",
           "Leaf tips brown and curled → too much feed; water plain for a round.",
           "The net about 70 % full (usually 4–6 weeks of veg) → flip to flower: Settings → Change stage → Flower (the light switches to 12 h by itself). The plants roughly double in the first 3 weeks of flower."],
          "22–28 °C day, 60–70 % RH easing to 55–65 % after two weeks (VPD 0.8–1.2), 18 h light"),
    Phase("flower_stretch", "Flower: the stretch", "Weeks 1–3 of 12/12: it grows 1.5–2× taller", 49, 70,
          ["Change the stage to Flower in the app: the light goes to 12/12 and the humidity eases down over a few days.",
           "First days: lollipop the bottom third (small branches below the net never make real buds).",
           "Keep tucking tops under the net. If one races ahead, pinch-bend it (supercrop) and tuck it back to canopy height.",
           "Switch to a bloom feed over two weeks; still pH 6.3–6.5 and let the pot dry between waterings.",
           "Smell starts around week 3: the exhaust must stay ducted out of the tent. A carbon filter on it (about CA$60) stops the smell if that matters where you live.",
           "Never turn the light on during the 12 dark hours."],
          ["Pistils (white hairs) at the nodes by day 10–14 → normal, it's flowering.",
           "Plant hitting the light → raise the light or bend the tops down.",
           "Stretch stops around day 21 → move on."],
          "22–27 °C day, 50–60 % RH (VPD 1.0–1.3), 12 h light, dark hours untouched"),
    Phase("flower_bulk", "Flower: bulking", "Weeks 4–7: buds fatten", 70, 98,
          ["Day 21 defoliation: remove the big fan leaves shading bud sites and anything growing below the net (at most 20–30 % of the leaves).",
           "Full-strength bloom feed if the plant is taking it well; watch the leaf tips.",
           "Keep RH under 50 %: dense buds and high humidity = bud rot. The exhaust does most of this.",
           "Support heavy branches with string or a stake.",
           "Photos: the advisor will ask for a bud close-up and a whole-plant shot each week."],
          ["Brown or grey spots inside a bud, or a bud that pulls apart mushy → bud rot: cut it out, drop RH, more airflow.",
           "Yellowing lower fan leaves late in this phase → normal; the plant is spending them."],
          "21–26 °C day, 45–52 % RH (VPD 1.2–1.4), 12 h light"),
    Phase("flower_ripen", "Flower: ripening", "Weeks 8–9: colour, smell and trichomes", 98, 107,
          ["Stop misting or foliar anything. Keep RH low and air moving.",
           "Check trichomes with a 60× jeweller's loupe on the bud (not the leaf): clear = wait, mostly cloudy = peak, 10–15 % amber = harvest window.",
           "Take the photos the advisor asks for: pistils and a trichome shot help it time the harvest.",
           "Reduce feed to half strength."],
          ["Most pistils orange and curled in + cloudy trichomes → start the flush.",
           "Sudden strong smell → check the exhaust duct is still attached; a carbon filter is the only thing that removes smell."],
          "20–25 °C day with cooler nights, 40–48 % RH (VPD 1.3–1.6), 12 h light"),
    Phase("flush", "Flush", "The last 7 days: plain water only", 107, 114,
          ["Water with plain water only (pH 6.3–6.5 if you have a kit by then), to good runoff.",
           "Let the leaves yellow: that's the plant using its reserves.",
           "Some growers give 24–48 h of darkness before the chop; optional."],
          ["Trichomes hit ~10–15 % amber → harvest day. Cut in the morning before lights-on if you can."],
          "20–24 °C day, 40–45 % RH, 12 h light"),
    Phase("dry", "Drying", "Slow and cool, 7–14 days", 114, 124,
          ["Cut the whole plant or big branches, trim the large fan leaves, hang in the dark tent.",
           "Set the stage to Drying in the app: lights stay off, fans keep air moving gently (not blowing on the buds).",
           "Aim for 16–20 °C and 55–62 % RH. Slow drying = better smell."],
          ["Small stems snap instead of bending → done drying, trim and jar it.",
           "Any sign of mould → more airflow, lower RH, cut out the affected part."],
          "16–20 °C, 55–62 % RH, dark"),
    Phase("cure", "Curing", "Jars for 2–4+ weeks", 124, 152,
          ["Trim, put in glass jars ¾ full with a 62 % humidity pack, in a dark cupboard.",
           "Week 1: open the jars for 10 minutes every day. Week 2+: every few days.",
           "Set the stage to Curing in the app: lights, humidifier and exhaust go idle."],
          ["Buds smell like hay or ammonia when opened → too wet; leave the jar open for an hour.",
           "After 3–4 weeks the smell is deep and clean → ready. It keeps improving for months."],
          "18–22 °C, 62 % RH, dark"),
]

_KEYS = [p.key for p in PHASES]


def current_phase_key(stage: str, day_in_stage: int, planted: bool) -> str | None:
    if stage == "seedling":
        return "seedling" if (planted or day_in_stage >= 10) else "germination"
    if stage == "veg":
        return "veg"
    if stage == "flower":
        return "flower_stretch" if day_in_stage < 21 else "flower_bulk" if day_in_stage < 49 else "flower_ripen"
    if stage == "flush":
        return "flush"
    if stage == "drying":
        return "dry"
    if stage == "curing":
        return "cure"
    return None  # done


def build_plan(profile: dict, today: date, day_in_stage: int, day_total: int, planted: bool,
               planted_on: date | None = None) -> dict:
    stage = profile.get("stage", "seedling")
    cur = current_phase_key(stage, day_in_stage, planted)
    cur_idx = _KEYS.index(cur) if cur else len(_KEYS)
    start = _pdate(profile.get("start_date"))
    flower_start = _pdate(profile.get("flower_start_date"))
    stage_started = _pdate(profile.get("stage_started"))
    expected_flower = int(profile.get("expected_flower_days") or 65)

    # Nominal day offsets, then anchor on real dates where we have them.
    starts = {p.key: p.start_day for p in PHASES}
    ends = {p.key: p.end_day for p in PHASES}
    if start:
        # If the current stage started on a known date, slide the schedule so it lines up.
        anchor_key = {"veg": "veg", "flush": "flush", "drying": "dry", "curing": "cure"}.get(stage)
        if anchor_key and stage_started:
            delta = (stage_started - start).days - starts[anchor_key]
            for k in _KEYS[_KEYS.index(anchor_key):]:
                starts[k] += delta
                ends[k] += delta
        # Seedling and veg count from the day it was planted, not the day it went into the towel.
        if stage in ("seedling", "veg") and not flower_start:
            shift = 0
            if planted_on:
                shift = (planted_on - start).days - starts["seedling"]
            elif cur == "germination" and day_total >= ends["germination"]:
                shift = day_total + 1 - ends["germination"]     # still waiting for the root: "next" is tomorrow at the earliest
            if shift and not (stage == "veg" and stage_started):
                ends["germination"] += shift
                for k in ("seedling", "veg", "flower_stretch", "flower_bulk", "flower_ripen", "flush", "dry", "cure"):
                    starts[k] += shift
                    ends[k] += shift
        if flower_start:
            f0 = (flower_start - start).days
            harvest = f0 + expected_flower
            starts.update(flower_stretch=f0, flower_bulk=f0 + 21, flower_ripen=f0 + 49, flush=harvest - 7, dry=harvest, cure=harvest + 10)
            ends.update(flower_stretch=f0 + 21, flower_bulk=f0 + 49, flower_ripen=harvest - 7, flush=harvest, dry=harvest + 10, cure=harvest + 38)
            ends["veg"] = f0

    phases = []
    for i, p in enumerate(PHASES):
        d = asdict(p)
        d["start_day"], d["end_day"] = starts[p.key], ends[p.key]
        d["start_date"] = (start + timedelta(days=starts[p.key])).isoformat() if start else None
        d["end_date"] = (start + timedelta(days=ends[p.key])).isoformat() if start else None
        d["status"] = "done" if i < cur_idx else "current" if i == cur_idx else "upcoming"
        phases.append(d)
    return {
        "start_date": profile.get("start_date"),
        "today": today.isoformat(),
        "day_total": day_total,
        "current_phase": cur,
        "phases": phases,
    }


def plan_for_prompt() -> str:
    """Compact plan text for the advisor's system prompt (static, so it caches)."""
    lines = ["# The grow plan (what the app shows the grower; keep your advice consistent with it)"]
    for p in PHASES:
        lines.append(f"## {p.title} (days {p.start_day}–{p.end_day}; {p.environment})")
        lines.append("Do: " + " ".join(p.what))
        lines.append("Watch for: " + " ".join(p.watch_for))
    return "\n".join(lines)


def _pdate(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None
