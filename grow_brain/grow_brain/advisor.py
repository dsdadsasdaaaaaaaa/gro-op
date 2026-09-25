"""Claude-powered grow advisor.

All calls go through `client.beta.messages.parse` with a Pydantic output schema, adaptive thinking
(the model default), a cached system prompt, and server-side refusal fallbacks.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Optional, TypeVar
from zoneinfo import ZoneInfo

import anthropic
from pydantic import BaseModel

from . import followups
from .controller import Controller, light_window
from .devices import ROLE_BY_NAME
from .models import BriefOut, ChatOut, LogAdviceOut, PhotoAnalysisOut, TargetChange
from .prompts import SYSTEM_PROMPT, units_instruction
from .store import Store, iso, parse_iso, utcnow
from .targets import ADJUSTABLE_BY_ADVISOR, BOUNDS, c_to_f, light_power_target

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens: (input, output, cache read, cache write 5 min). Anthropic first-party list prices.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.25, 12.5),
    "claude-fable-5": (10.0, 50.0, 1.0, 12.5),
    "claude-opus-5-5": (4.0, 20.0, 0.2, 5.0),
    "claude-opus-5": (5.0, 25.0, 0.5, 6.25),
    "claude-opus-4-8": (5.0, 25.0, 0.5, 6.25),
    "claude-opus-4-7": (5.0, 25.0, 0.5, 6.25),
    "claude-opus-4-6": (5.0, 25.0, 0.5, 6.25),
    "claude-sonnet-5": (2.0, 10.0, 0.2, 2.5),
    "claude-sonnet-4-6": (3.0, 15.0, 0.3, 3.75),
    "claude-haiku-4-5": (1.0, 5.0, 0.1, 1.25),
}
MODELS = list(PRICES)
NO_EFFORT = {"claude-haiku-4-5"}          # this model rejects output_config.effort
INTERACTIVE = {"chat", "log", "photo", "look_now"}   # a person is waiting on a phone (app timeout 90 s)


def _cost(model: str, inp: int, out: int, cache_read: int, cache_write: int) -> float:
    p = PRICES.get(model) or next((v for k, v in PRICES.items() if model.startswith(k)), PRICES["claude-opus-5"])
    return (inp * p[0] + out * p[1] + cache_read * p[2] + cache_write * p[3]) / 1_000_000


class AdvisorError(Exception):
    pass


class Advisor:
    def __init__(self, store: Store, controller: Controller, api_key: Optional[str], default_model: str, notifier, photo_dir: Path,
                 camera=None):
        self.store = store
        self.camera = camera
        self.controller = controller
        self.notifier = notifier
        self.photo_dir = photo_dir
        self.default_model = default_model
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=300.0, max_retries=2) if api_key else None

    @property
    def enabled(self) -> bool:
        return self.client is not None

    # ------------------------------------------------------------------ context building

    async def _context(self) -> tuple[str, dict]:
        """A compact, human-readable snapshot of everything the advisor should know."""
        settings = await self.controller.settings()
        profile = await self.controller.profile()
        tz = self.controller.tz(settings)
        now_local = datetime.now(tz)
        targets, day_in_stage, day_total = await self.controller.effective_targets(profile, settings)
        units = settings.get("units", "c")

        def tf(c: Optional[float]) -> str:
            if c is None:
                return "–"
            return f"{c_to_f(c):.1f}°F" if units == "f" else f"{c:.1f}°C"

        sensor = self.controller.sensor
        lines = [f"Local time: {now_local.strftime('%Y-%m-%d %H:%M')} ({settings.get('timezone')})",
                 f"Home Assistant connected: {self.controller.ha_ok}", ""]
        plants = await self.store.plants()
        pname = {p["id"]: p["name"] for p in plants}
        today = now_local.date()
        lines.append("## Tent")
        lines.append(f"- Stage: {profile['stage']} (day {day_in_stage} of stage, since {profile.get('stage_started') or 'unknown'})")
        from .plan import PHASES, current_phase_key
        entries_all = await self.store.log_entries(300)
        lines += ["", "## Plants (use these ids in plant_id)"]
        for p in plants:
            from datetime import date as _date
            try:
                dt = (today - _date.fromisoformat(p["start_date"])).days if p.get("start_date") else None
            except ValueError:
                dt = None
            mine = [e for e in entries_all if e.get("plant_id") in (p["id"], None)]
            planted = next((e["created_at"][:10] for e in reversed(mine) if e["kind"] == "planted"
                            or (e.get("context") or "").lower() in ("planted", "planting")), None)
            moved = next((e["created_at"][:10] for e in reversed(mine) if e["kind"] == "transplant"), None)
            where = (f"in its {p['pot_size_l']:g} L pot since {moved}" if moved else
                     f"planted in a 0.5 L cup on {planted}" if planted else "not planted yet (seed germinating)")
            phase_key = current_phase_key(profile["stage"], day_in_stage, bool(planted or moved))
            phase = next((ph.title for ph in PHASES if ph.key == phase_key), profile["stage"])
            lines.append(f"- plant_id={p['id']}: \"{p['name']}\" owned by {p['owner'] or 'unknown'}; {p['strain']} ({p['breeder']}), "
                         f"{p['seed_type']}, {p['medium']}; {where}; plan phase: {phase}; started {p.get('start_date') or 'unknown'}"
                         + (f" → day {dt}" if dt is not None else "") + (f"; notes: {p['notes']}" if p.get("notes") else ""))
        if not plants:
            lines.append("- none registered yet")
        if profile.get("flower_start_date"):
            lines.append(f"- Flower started {profile['flower_start_date']}; expected ~{profile['expected_flower_days']} days of flower")
        lines.append(f"- Exhaust ducted outside the tent: {'yes' if profile.get('exhaust_ducted') else 'NO (not connected yet)'}")
        if profile.get("notes"):
            lines.append(f"- Grower notes: {profile['notes']}")

        cam = await self.camera.info() if self.camera else None
        if cam:
            lines.append(f"- Fixed tent camera: {cam['name']} ({'online' if cam['available'] else 'offline'}); you receive its latest frame with the daily brief and when the grower taps 'look now'.")
        lines += ["", "## Equipment mapped in Home Assistant"]
        dmap = await self.store.get_device_map()
        for role, rd in ROLE_BY_NAME.items():
            if role in dmap:
                st = self.controller.states.get(dmap[role], {})
                reason = self.controller.last_reasons.get(role, "")
                lines.append(f"- {rd.label}: {st.get('state', '?')}" + (f" ({reason})" if reason else ""))
        missing = [rd.label for role, rd in ROLE_BY_NAME.items() if role not in dmap and rd.kind == "switch"]
        if missing:
            lines.append(f"- NOT available: {', '.join(missing)}")

        lines += ["", "## Right now"]
        if sensor.stale:
            lines.append("- SENSOR STALE / MISSING — automation is in safe mode")
        lines.append(f"- Air {tf(sensor.temp_c)}, RH {sensor.humidity if sensor.humidity is not None else '–'}%, VPD {sensor.vpd_kpa if sensor.vpd_kpa is not None else '–'} kPa" + (f", CO2 {sensor.co2:.0f} ppm" if sensor.co2 else ""))
        lines.append(f"- Targets (day band, source={targets.source}): temp {tf(targets.temp_min_c)}–{tf(targets.temp_max_c)}, RH {targets.humidity_min:g}–{targets.humidity_max:g}%, VPD {targets.vpd_min}–{targets.vpd_max} kPa, light {targets.light_hours:g} h from {targets.light_on_time}; night band is ~{targets.night_temp_drop_c:g}° cooler. {targets.note}")
        lpt = light_power_target(profile.get("stage") or "", day_in_stage)
        if lpt:
            w = self.controller.power_w("light", await self.store.get_device_map())
            now_w = "unknown" if w is None else ("off right now (dark hours)" if w < 15 else f"{w:.0f} W")
            lines.append(f"- Light power at the light plug: {now_w}; this phase wants about {lpt[0]:.0f}–{lpt[1]:.0f} W ({lpt[2]}). "
                         "If it's more than ~10 % off while the lights are on, say exactly what to change (dimmer, which light to plug "
                         "in); the app confirms it on the plug.")
        paused = await self.controller.paused_until()
        if paused:
            lines.append(f"- Automation PAUSED until {paused}")
        if await self.controller.standby():
            lines.append("- TENT IN STANDBY: every device is off on purpose (nothing planted in it yet). Don't flag the environment as a problem; say what to prepare and when to start the tent.")

        lines += ["", "## Last 24 h"]
        lines.append(_summarise_readings(await self.store.readings_since(24), units, tz=tz,
                                         schedule=(targets.light_on_time, targets.light_hours)))
        lines.append(_summarise_device_log(await self.store.device_log_since(24)))
        lines += ["", "## Last 7 days (daily)"]
        readings7 = await self.store.readings_since(24 * 7)
        for day, rows in _group_by_day(readings7, tz).items():
            lines.append(f"- {day}: " + _summarise_readings(rows, units, short=True))

        lines += ["", "## Grower's log (newest first)"]
        entries = await self.store.log_entries(25)
        if not entries:
            lines.append("- nothing logged yet")
        for e in entries:
            v = f" {e['value']:g}{(' ' + e['unit']) if e['unit'] else ''}" if e["value"] is not None else ""
            ctxs = f" [{e['context']}]" if e.get("context") else ""
            note = f" – {e['note']}" if e.get("note") else ""
            who = f"[{pname.get(e.get('plant_id'), 'tent')}] "
            lines.append(f"- {e['created_at'][:16]} {who}{e['kind']}{v}{ctxs}{note}")

        lines += ["", "## Open tasks"]
        tasks = await self.store.tasks("open")
        lines += [f"- #{t['id']} [{pname.get(t.get('plant_id'), 'tent')}] {t['title']}" + (f" (due {t['due']})" if t["due"] else "") for t in tasks] or ["- none"]
        recent_done = [t for t in await self.store.tasks("done", limit=40)
                       if t.get("completed_at") and t["completed_at"] >= (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()[:19]]
        if recent_done:
            lines += ["", "## Done in the last 3 days (don't ask for these again)"]
            lines += [f"- [{pname.get(t.get('plant_id'), 'tent')}] {t['title']} (done {t['completed_at'][:16]})" for t in recent_done]
        lines += ["", "## Open photo requests"]
        prs = await self.store.photo_requests("open")
        lines += [f"- #{p['id']} [{pname.get(p.get('plant_id'), 'tent')}] {p['title']} (asked {p['created_at'][:10]})" for p in prs] or ["- none"]

        lines += ["", "## Recent photo analyses"]
        photos = [p for p in await self.store.photos(5) if p.get("analysis")]
        for p in photos:
            a = p["analysis"]
            lines.append(f"- {p['created_at'][:10]} [{pname.get(p.get('plant_id'), 'tent')}] health {a.get('health_score')}/10: {a.get('summary')}")
        if not photos:
            lines.append("- none yet")

        lines += ["", "## Recent briefs"]
        for b in await self.store.recent_briefs(3):
            lines.append(f"- {b['created_at'][:10]}: {b.get('headline')} — {b.get('summary', '')[:300]}")

        lines += ["", "## Warnings/alerts (last 48 h)"]
        evs = await self.store.events(15, min_level="warn", hours=48)
        lines += [f"- {e['at'][:16]} {e['level']}: {e['message']}" for e in evs] or ["- none"]

        return "\n".join(lines), settings

    # ------------------------------------------------------------------ Claude calls

    async def month_spend(self, settings: dict) -> float:
        tz = self.controller.tz(settings)
        month_start = datetime.now(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        from .store import iso
        return (await self.store.usage_summary(iso(month_start)))["usd"]

    def model_for(self, settings: dict) -> str:
        model = settings.get("model") or self.default_model
        if model not in PRICES:
            if not getattr(self, "_model_warned", None) == model:
                self._model_warned = model
                log.warning("Unknown model %r in settings: using %s", model, self.default_model)
            model = self.default_model if self.default_model in PRICES else "claude-opus-5"
        return model

    async def _parse(self, output_model: type[T], user_content: Any, settings: dict, history: list[dict] | None = None,
                     effort: str = "high", max_tokens: int = 16000, kind: str = "other") -> T:
        if not self.client:
            raise AdvisorError("Advisor is off: add your Anthropic API key in the add-on configuration.")
        budget = float(settings.get("advisor_budget_usd") or 40.0)
        spent = await self.month_spend(settings)
        if spent >= budget:
            raise AdvisorError(f"This month's advisor budget (${budget:.0f}) is used up (${spent:.2f} spent). "
                               f"The tent keeps running on its own; raise the budget in Settings if you need more.")
        model = self.model_for(settings)
        system = [
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": units_instruction(settings.get("units", "c"))},
        ]
        messages = list(history or []) + [{"role": "user", "content": user_content}]
        kwargs: dict[str, Any] = dict(model=model, max_tokens=max_tokens, system=system, messages=messages,
                                      output_format=output_model)
        if model not in NO_EFFORT:
            kwargs["output_config"] = {"effort": effort}
        # someone is waiting on a phone: fail fast instead of outliving the app's 90 s timeout
        client = self.client.with_options(timeout=85.0, max_retries=0) if kind in INTERACTIVE else self.client
        try:
            try:
                resp = await client.beta.messages.parse(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except anthropic.BadRequestError as e:
                if "fallback" not in str(e).lower():
                    raise
                log.info("Server-side fallbacks not accepted here; retrying without them")
                resp = await client.beta.messages.parse(**kwargs)
        except anthropic.AuthenticationError:
            raise AdvisorError("Anthropic API key was rejected. Check it in the add-on configuration.")
        except anthropic.RateLimitError:
            raise AdvisorError("Claude is rate-limited right now. Try again in a minute.")
        except anthropic.APITimeoutError:
            raise AdvisorError("Claude took too long to answer. Try again; a shorter question helps.")
        except anthropic.APIStatusError as e:
            raise AdvisorError(f"Claude API error ({e.status_code}): {e.message}")
        except anthropic.APIConnectionError:
            raise AdvisorError("Could not reach the Claude API. Is the Home Assistant box online?")
        except Exception as e:   # the SDK validating a malformed reply, or anything else unexpected
            log.exception("advisor call failed")
            raise AdvisorError(f"Could not understand Claude's reply ({type(e).__name__}). Try again.")
        # pay for what was used even when the answer is unusable
        u = resp.usage
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        served = getattr(resp, "model", model) or model
        usd = _cost(served, u.input_tokens, u.output_tokens, cr, cw)
        await self.store.add_usage(kind, served, u.input_tokens, cr, cw, u.output_tokens, usd)
        log.info("advisor %s: in=%s cached=%s out=%s ≈$%.3f", output_model.__name__, u.input_tokens, cr, u.output_tokens, usd)
        if resp.stop_reason == "refusal":
            raise AdvisorError("Claude declined to answer this one. Try rephrasing.")
        if resp.stop_reason == "max_tokens":
            raise AdvisorError("The answer was cut off. Try again.")
        parsed = getattr(resp, "parsed_output", None)
        if parsed is None:
            text = next((b.text for b in resp.content if b.type == "text"), "")
            try:
                parsed = output_model.model_validate_json(text)
            except Exception as e:
                raise AdvisorError(f"Could not understand Claude's reply: {e}")
        return parsed

    # ------------------------------------------------------------------ applying what Claude asked for

    async def _apply(self, out: BaseModel, settings: dict, source: str, default_plant_id: int | None = None) -> dict:
        """Persist tasks / photo requests / target changes from a structured reply. Returns API-shaped dicts."""
        created_tasks, created_prs, applied_changes = [], [], []
        plants = {p["id"]: p for p in await self.store.plants()}

        def pid_of(draft):
            pid = getattr(draft, "plant_id", None)
            if pid in plants:
                return pid
            return default_plant_id if default_plant_id in plants else None
        open_tasks = await self.store.tasks("open")
        open_ids = {t["id"] for t in open_tasks}
        closed = []
        system_ids = {t["id"] for t in open_tasks if t.get("created_by") == "system"}
        for tid in getattr(out, "tasks_done", []) or []:
            if tid in open_ids and tid not in system_ids:
                await self.store.set_task_status(tid, "done")
                closed.append(tid)
        if closed:
            await self.store.add_event("info", "advisor", f"Advisor closed task(s) {', '.join('#' + str(t) for t in closed)}")
        open_titles = [(t.get("plant_id"), _words(t["title"])) for t in open_tasks if t["id"] not in closed]
        for td in getattr(out, "tasks", []) or []:
            pid, words = pid_of(td), _words(td.title)
            # same job already open for this plant or for the whole tent → don't add a near-duplicate
            if any((op == pid or op is None or pid is None) and _similar(words, ow) for op, ow in open_titles):
                continue
            created_tasks.append(await self.store.add_task(td.title, td.detail, td.due, td.priority, "advisor", pid))
            open_titles.append((pid, words))
        open_pr_titles = {(p.get("plant_id"), p["title"].strip().lower()) for p in await self.store.photo_requests("open")}
        for pd in getattr(out, "photo_requests", []) or []:
            key = (pid_of(pd), pd.title.strip().lower())
            if key in open_pr_titles:
                continue
            created_prs.append(await self.store.add_photo_request(pd.title, pd.instructions, pd.reason, key[0]))
        for pn in getattr(out, "plant_notes", []) or []:
            plant = plants.get(pn.plant_id)
            note = (pn.note or "").strip()
            if plant and note and note.lower() not in (plant.get("notes") or "").lower():
                merged = ((plant.get("notes") or "").rstrip(". ") + ". " if plant.get("notes") else "") + note
                await self.store.update_plant(pn.plant_id, notes=merged[-1500:])
        recorded = await self._apply_plantings(getattr(out, "plantings", []) or [], plants, settings)
        sprouts = await self._apply_sprouts(getattr(out, "sprouted", []) or [], plants, source)
        changes: list[TargetChange] = getattr(out, "target_changes", []) or []
        if changes:
            applied_changes = await self._apply_target_changes(changes, settings, source)
        if created_prs:
            by_plant: dict = {}
            for pr in created_prs:
                by_plant.setdefault(pr.get("plant_id"), []).append(pr["title"])
            for pid, titles in by_plant.items():
                plant = plants.get(pid)
                svc = plant.get("notify_service") if plant else None
                who = f" for {plant['name']}" if plant else ""
                url = f"growop://photos?plant={pid}" if pid else "growop://photos"
                await self.notifier.send(f"photo_request:{pid}", f"The advisor would like {len(titles)} photo(s){who}: " + "; ".join(titles),
                                         title="Photo request", url=url, service=svc, everyone=svc is None)
        return {"tasks": created_tasks, "photo_requests": created_prs, "target_changes": applied_changes, "tasks_done": closed,
                "plantings": recorded, "sprouted": sprouts}

    async def _apply_sprouts(self, plant_ids: list, plants: dict, source: str) -> list[int]:
        """First sight of a seedling above the soil: log the day, tell both phones, date the dome removal from it,
        and once every plant is up, close the daily 'check for sprouts' job."""
        if not plant_ids:
            return []
        entries = await self.store.log_entries(500)
        already = {e.get("plant_id") for e in entries if e["kind"] == "sprouted"}
        seen_by = "the tent camera" if source == "camera_check" else "a photo"
        new = []
        for pid in dict.fromkeys(plant_ids):
            if pid not in plants or pid in already:
                continue
            await self.store.add_log_entry("sprouted", None, None, "advisor", f"Sprouted: first seen by {seen_by}", pid)
            await followups.sprouted(self.store, self.controller, pid)
            await self.notifier.send(f"sprouted:{pid}", f"{plants[pid]['name']} has sprouted! It's through the soil. "
                                     "Keep the dome on until the first jagged leaves open.", title="Grow tent",
                                     url=f"growop://photos?plant={pid}", everyone=True)
            new.append(pid)
            already.add(pid)
        if new and all(p in already for p in plants):
            for t in await self.store.tasks("open"):
                if "sprout" in t["title"].lower() and t.get("created_by") != "system":
                    await self.store.set_task_status(t["id"], "done")
        if new:
            await self.store.add_event("info", "advisor", "Sprouted: " + ", ".join(plants[p]["name"] for p in new))
        return new

    async def _apply_plantings(self, plantings: list, plants: dict, settings: dict) -> list[dict]:
        """Record a planting or transplant the grower reported, dated the day it happened, so the plan counts from it.
        A record of the same kind on another day is corrected rather than doubled."""
        if not plantings:
            return []
        tz = self.controller.tz(settings)
        today = datetime.now(tz).date()
        entries = await self.store.log_entries(500)
        done = []
        for pl in plantings:
            if pl.plant_id not in plants:
                continue
            try:
                day = date.fromisoformat((pl.date or "").strip()[:10])
            except ValueError:
                continue
            if day > today or day < today - timedelta(days=60):
                continue
            at = datetime.now(timezone.utc) if day == today else datetime(day.year, day.month, day.day, 12, tzinfo=tz)
            at_iso = iso(at.astimezone(timezone.utc))
            what = "Planted" if pl.kind == "planted" else "Moved to the big pot"
            same = sorted((e for e in entries if e["kind"] == pl.kind and e.get("plant_id") == pl.plant_id), key=lambda e: e["created_at"])
            if same:
                first = same[0]
                ts = parse_iso(first["created_at"])
                if ts and ts.astimezone(tz).date() == day:
                    continue
                await self.store.redate_log_entry(first["id"], at_iso, f"{what} on {day} (date corrected by the advisor)")
            else:
                await self.store.add_log_entry(pl.kind, None, None, "advisor", f"{what} on {day} (recorded by the advisor)", pl.plant_id, at=at_iso)
                await followups.after_log(self.store, self.controller, pl.kind, pl.plant_id)
            done.append({"plant_id": pl.plant_id, "kind": pl.kind, "date": day.isoformat()})
        if done:
            await self.store.add_event("info", "advisor", "Advisor recorded: " + "; ".join(
                f"{plants[d['plant_id']]['name']} {d['kind']} {d['date']}" for d in done))
        return done

    async def _apply_target_changes(self, changes: list[TargetChange], settings: dict, source: str) -> list[dict]:
        targets, _, _ = await self.controller.effective_targets()
        override = await self.store.get_kv("targets_override", None) or {"values": {}, "source": "advisor"}
        values = dict(override.get("values", {}))
        out = []
        auto = bool(settings.get("auto_apply_advisor_targets", True))
        today = datetime.now(self.controller.tz(settings)).date().isoformat()
        used = await self.store.get_kv("advisor_nudges", {}) or {}
        if used.get("date") != today:
            used = {"date": today, "delta": {}}
        for ch in changes:
            if ch.field not in ADJUSTABLE_BY_ADVISOR:
                continue
            lo, hi = BOUNDS[ch.field]
            current = getattr(targets, ch.field)
            to = float(ch.to)
            if "temp" in ch.field and to > 45:     # written in °F by mistake
                to = (to - 32) * 5 / 9
            new = float(min(max(to, lo), hi))
            # at most 2 °C / 5 % RH of movement per field per day, however many replies ask for it
            limit = 2.0 if "temp" in ch.field else 5.0
            already = float(used["delta"].get(ch.field, 0.0))
            new = max(current - (limit + already), min(current + (limit - already), new))
            new = round(new, 1)
            if new == current:
                continue
            used["delta"][ch.field] = round(already + (new - current), 2)
            rec = {"field": ch.field, "from": current, "to": new, "reason": ch.reason, "applied": auto}
            out.append(rec)
            if auto:
                values[ch.field] = new
        if auto and out:
            await self.store.set_kv("advisor_nudges", used)
            await self.store.set_kv("targets_override", {"values": values, "source": "advisor",
                                                         "phase": await self.controller.phase_key(),
                                                         "light_on_time": override.get("light_on_time", targets.light_on_time)})
            for rec in out:
                await self.store.add_event("info", "advisor", f"Advisor set {rec['field']} {rec['from']} → {rec['to']}: {rec['reason']}")
        return out

    # ------------------------------------------------------------------ public operations

    async def daily_brief(self) -> dict:
        ctx, settings = await self._context()
        plants = await self.store.plants()
        prompt = (f"{ctx}\n\n---\nWrite today's brief. The shared headline/summary/concerns/actions cover the tent. "
                  f"Then fill per_plant with exactly one entry for each plant_id listed above ({', '.join(str(p['id']) for p in plants) or 'none'}): "
                  f"what its owner should do for THAT plant today, addressed to them by name. Ask for a photo only when it would change your advice. "
                  f"Only include target_changes if the data clearly justifies them.")
        content: Any = prompt
        frame = await self.camera.latest_frame_for_advisor() if self.camera else None
        if frame:
            img, when = frame
            content = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(img).decode()}},
                {"type": "text", "text": prompt + f"\n\nThe image is the latest frame from the fixed tent camera (taken {when[:16]} UTC, wide view of the whole tent). Use it: comment on what you can actually see; if it's dark or empty say so."},
            ]
        out = await self._parse(BriefOut, content, settings, effort="high", kind="brief")
        applied = await self._apply(out, settings, "brief")
        data = out.model_dump()
        data["camera_frame_at"] = frame[1] if frame else None
        pname = {p["id"]: p["name"] for p in plants}
        data["per_plant"] = [{**pb, "name": pname.get(pb["plant_id"], "")} for pb in data.get("per_plant", []) if pb["plant_id"] in pname]
        data.update(applied)
        brief = await self.store.add_brief(data)
        await self.store.add_event("info", "advisor", f"Daily brief: {out.headline}")
        await self.notifier.send("brief", out.headline, title="Today's grow brief", url="growop://advisor", everyone=True)
        return brief

    async def advise_on_log(self, entry: dict) -> dict:
        ctx, settings = await self._context()
        v = f"{entry['value']:g}{(' ' + entry['unit']) if entry.get('unit') else ''}" if entry.get("value") is not None else ""
        plant = await self.store.get_plant(entry["plant_id"]) if entry.get("plant_id") else None
        who = f"{plant['owner'] or 'The grower'} just logged for plant_id={plant['id']} (\"{plant['name']}\")" if plant else "The grower just logged (tent-wide)"
        prompt = (f"{ctx}\n\n---\n{who}: kind={entry['kind']} {v} "
                  f"context={entry.get('context') or '-'} note={entry.get('note') or '-'}.\n"
                  f"Tell them what this means and exactly what to do next. Tasks/photo requests are for this plant unless clearly tent-wide.")
        out = await self._parse(LogAdviceOut, prompt, settings, effort="medium", kind="log")
        applied = await self._apply(out, settings, "log", default_plant_id=entry.get("plant_id"))
        advice = out.model_dump()
        advice.update(applied)
        await self.store.set_log_advice(entry["id"], advice)
        if out.urgency == "urgent":
            await self.notifier.send("urgent_log", out.summary, title="Grow: act now", url="growop://log",
                                     service=(plant or {}).get("notify_service"), everyone=not (plant or {}).get("notify_service"))
        return advice

    async def analyse_photo(self, photo_id: int, image_path: Path, media_type: str, request: dict | None, note: str | None,
                            plant_id: int | None = None) -> dict:
        ctx, settings = await self._context()
        data = base64.standard_b64encode(image_path.read_bytes()).decode()
        plant = await self.store.get_plant(plant_id) if plant_id else None
        pl = f" It shows plant_id={plant['id']} (\"{plant['name']}\", {plant['owner'] or 'unknown owner'})." if plant else ""
        ask = ("This photo answers your request: "
               f"'{request['title']}' — {request['instructions']} (reason: {request['reason']}).{pl}") if request else \
              f"The grower sent this photo on their own.{pl}"
        if note:
            ask += f" Grower's note: {note}"
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": f"{ctx}\n\n---\n{ask}\nAnalyse the plant in the photo and say what to do."},
        ]
        out = await self._parse(PhotoAnalysisOut, content, settings, effort="high", kind="photo")
        applied = await self._apply(out, settings, "photo", default_plant_id=plant_id)
        analysis = out.model_dump()
        analysis.update(applied)
        await self.store.set_photo_analysis(photo_id, analysis)
        if request:
            await self.store.set_photo_request_status(request["id"], "done", photo_id)
        await self.store.add_event("info", "advisor", f"Photo analysed: health {out.health_score}/10 – {out.summary[:120]}")
        return analysis

    async def camera_check(self) -> dict | None:
        """Once a day, an hour after lights-on: look at the tent camera and only speak up if something is wrong."""
        if not self.camera:
            return None
        data = await self.camera.snapshot(max_age_s=0)
        if not data:
            raise AdvisorError("The tent camera didn't send a picture")
        import io
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as e:
            raise AdvisorError(f"The camera sent an image that couldn't be read ({e})")
        im.thumbnail((2000, 2000))
        pid = await self.store.add_photo(None, None, "", None, source="camera")
        path = self.photo_dir / f"{pid}.jpg"
        im.save(path, "JPEG", quality=88)
        thumb = im.copy(); thumb.thumbnail((400, 400)); thumb.save(self.photo_dir / f"{pid}_thumb.jpg", "JPEG", quality=80)
        await self.store.db.execute("UPDATE photos SET path=? WHERE id=?", (str(path), pid))
        await self.store.db.commit()
        ctx, settings = await self._context()
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(path.read_bytes()).decode()}},
            {"type": "text", "text": f"{ctx}\n\n---\nThis is the automatic daily camera check, one hour after lights-on. Look at both plants. "
                                     f"If a seedling has come up through the soil and the log doesn't show that plant as sprouted yet, put its "
                                     f"plant_id in `sprouted` (only if the plant notes or the grower's log say which cup is whose; otherwise describe it and ask them to log which cup is whose). "
                                     f"If everything looks normal, say so in one sentence with no findings and no tasks. Only report findings with severity "
                                     f"'warn' or 'alert' when you can actually see a problem (drooping, colour change, dry surface, pests, light too close, "
                                     f"something fallen over). Health score reflects what you can see."},
        ]
        out = await self._parse(PhotoAnalysisOut, content, settings, effort="medium", kind="camera_check")
        applied = await self._apply(out, settings, "camera_check")
        analysis = out.model_dump(); analysis.update(applied)
        await self.store.set_photo_analysis(pid, analysis)
        serious = [f for f in out.findings if f.severity in ("warn", "alert")]
        urgent = [f for f in out.findings if f.severity == "alert"]
        await self.store.resolve_alerts("advisor", "Camera check")   # today's check replaces yesterday's findings
        if serious or out.health_score < 6:
            msg = "; ".join(f.title for f in serious) or out.summary
            await self.store.add_event("warn", "advisor", f"Camera check: {msg}")
            if urgent or out.health_score < 5:   # a phone buzz only for something that can't wait for the morning brief
                await self.notifier.send("camera_check", "Camera check: " + "; ".join(f.title for f in (urgent or serious)),
                                         title="Grow tent", url="growop://photos", everyone=True)
        else:
            await self.store.add_event("info", "advisor", f"Camera check: {out.summary[:120]}")
        return analysis

    async def chat(self, message: str, plant_id: int | None = None, author: str | None = None) -> dict:
        ctx, settings = await self._context()
        history_rows = await self.store.chat_history(20)
        while history_rows and history_rows[0]["role"] != "user":
            history_rows = history_rows[1:]          # the API wants the history to open with a user turn
        history = []
        for r in history_rows:
            content = r["content"]
            if r["role"] == "user" and r.get("author") and not content.startswith("["):
                content = f"[{r['author']}] {content}"
            history.append({"role": r["role"], "content": content})
        plant = await self.store.get_plant(plant_id) if plant_id else None
        # The asker is whoever holds the phone; without that, assume the plant's owner is asking.
        asker = (author or "").strip() or (plant["owner"] if plant else None)
        if plant:
            who = f"{asker or 'Grower'} (asking about plant_id={plant['id']}, \"{plant['name']}\") says"
        else:
            who = f"{asker or 'Grower'} (asking about the whole tent) says"
        # Fresh context goes into the latest user turn so the cached system prompt stays stable.
        user = f"<current_state>\n{ctx}\n</current_state>\n\n{who}: {message}"
        await self.store.add_chat("user", message, author=asker or (plant["name"] if plant else None), plant_id=plant_id)
        out = await self._parse(ChatOut, user, settings, history=history, effort="medium", kind="chat")
        applied = await self._apply(out, settings, "chat", default_plant_id=plant_id)
        reply = out.reply
        extras = []
        if applied["tasks"]:
            extras.append("Added task(s): " + "; ".join(t["title"] for t in applied["tasks"]))
        if applied["photo_requests"]:
            extras.append("Photo request(s) added in the Photos tab: " + "; ".join(p["title"] for p in applied["photo_requests"]))
        if applied.get("plantings"):
            pname = {p["id"]: p["name"] for p in await self.store.plants()}
            extras.append("Recorded in the log: " + "; ".join(
                f"{pname.get(d['plant_id'], 'plant')} {'planted' if d['kind'] == 'planted' else 'moved to its big pot'} on {d['date']}"
                for d in applied["plantings"]))
        if applied["target_changes"]:
            names = {"temp_min_c": "lowest temperature", "temp_max_c": "highest temperature",
                     "humidity_min": "lowest humidity", "humidity_max": "highest humidity"}
            unit = lambda f: " °C" if "temp" in f else " %"
            extras.append("Changed the tent settings: " + "; ".join(f"{names.get(c['field'], c['field'])} now {c['to']:g}{unit(c['field'])}"
                                                                   for c in applied["target_changes"] if c["applied"]))
        if extras:
            reply += "\n\n" + "\n".join(extras)
        mid = await self.store.add_chat("assistant", reply)
        return {"id": mid, "reply": reply}


# ---------------------------------------------------------------------- helpers

def _summarise_readings(rows: list[dict], units: str, short: bool = False, tz=None, schedule=None) -> str:
    if not rows:
        return "- no sensor data"
    temps = [r["temp_c"] for r in rows if r["temp_c"] is not None]
    hums = [r["humidity"] for r in rows if r["humidity"] is not None]
    vpds = [r["vpd_kpa"] for r in rows if r["vpd_kpa"] is not None]
    lit = [r for r in rows if r.get("light_on")]

    def t(c):
        return f"{c_to_f(c):.0f}°F" if units == "f" else f"{c:.1f}°C"

    parts = []
    if temps:
        parts.append(f"temp {t(min(temps))}–{t(max(temps))} avg {t(mean(temps))}")
    if hums:
        parts.append(f"RH {min(hums):.0f}–{max(hums):.0f}% avg {mean(hums):.0f}%")
    if vpds:
        parts.append(f"VPD {min(vpds):.2f}–{max(vpds):.2f} avg {mean(vpds):.2f}")
    if lit and not short:
        day_t = [r["temp_c"] for r in lit if r["temp_c"] is not None]
        night = [r for r in rows if r.get("light_on") == 0]
        night_t = [r["temp_c"] for r in night if r["temp_c"] is not None]
        if day_t and night_t:
            parts.append(f"lights-on avg {t(mean(day_t))} / lights-off avg {t(mean(night_t))}")
    timed = [r for r in rows if r.get("temp_c") is not None and parse_iso(r.get("t"))]
    if timed and tz is not None and not short:
        # when the extremes happened, so a cold afternoon with the tent off isn't read as a cold night
        def when(r):
            at = parse_iso(r["t"]).astimezone(tz)
            if r.get("light_on"):
                state = "lights on"
            elif schedule and light_window(at, schedule[0], schedule[1])[0]:
                state = "light off during its scheduled hours: tent off or light switched off"
            else:
                state = "lights off, night"
            return f"{at:%a %H:%M}, {state}"
        lo = min(timed, key=lambda r: r["temp_c"])
        hi = max(timed, key=lambda r: r["temp_c"])
        parts.append(f"coldest {t(lo['temp_c'])} ({when(lo)}), warmest {t(hi['temp_c'])} ({when(hi)})")
    prefix = "" if short else "- "
    return prefix + ", ".join(parts) + ("" if short else f" ({len(rows)} readings)")


def _summarise_device_log(rows: list[dict]) -> str:
    if not rows:
        return "- no device switching recorded"
    counts: dict[str, int] = {}
    for r in rows:
        if r["state"] == "on":
            counts[r["role"]] = counts.get(r["role"], 0) + 1
    return "- device on-cycles: " + ", ".join(f"{ROLE_BY_NAME[k].label} ×{v}" for k, v in sorted(counts.items())) if counts else "- devices steady"


def _group_by_day(rows: list[dict], tz: ZoneInfo) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        ts = parse_iso(r["t"])
        if not ts:
            continue
        key = ts.astimezone(tz).strftime("%a %m-%d")
        out.setdefault(key, []).append(r)
    return out


_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "it", "its", "your", "with", "at", "levi's", "dad's",
         "levi", "dad", "plant", "seedling", "seed", "both", "each", "s", "about", "around", "new", "re", "tent"}
# different words for the same job ("Re-aim the camera" / "Point the camera down")
_SAME = {"point": "aim", "tilt": "aim", "angle": "aim", "lamp": "light", "led": "light", "panel": "light"}


def _words(title: str) -> set[str]:
    import re as _re
    out = set()
    for w in _re.findall(r"[a-z0-9']+", title.lower()):
        if w in _STOP or w.isdigit():
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]                     # cups → cup
        out.add(_SAME.get(w, w))
    return out


_OPPOSITES = (("up", "down"), ("off", "on"), ("raise", "lower"), ("more", "less"), ("increase", "decrease"),
              ("open", "close"), ("add", "remove"), ("higher", "lower"), ("warmer", "cooler"))


def _similar(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return a == b
    if any((x in a and y in b) or (y in a and x in b) for x, y in _OPPOSITES):
        return False                       # "turn the light down" is not the same job as "turn the light up"
    return len(a & b) / len(a | b) >= 0.5
