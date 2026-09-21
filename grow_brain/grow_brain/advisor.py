"""Claude-powered grow advisor.

All calls go through `client.beta.messages.parse` with a Pydantic output schema, adaptive thinking
(the model default), a cached system prompt, and server-side refusal fallbacks.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Optional, TypeVar
from zoneinfo import ZoneInfo

import anthropic
from pydantic import BaseModel

from .controller import Controller
from .devices import ROLE_BY_NAME
from .models import BriefOut, ChatOut, LogAdviceOut, PhotoAnalysisOut, TargetChange
from .prompts import SYSTEM_PROMPT, units_instruction
from .store import Store, parse_iso, utcnow
from .targets import ADJUSTABLE_BY_ADVISOR, BOUNDS, c_to_f

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


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
        lines += ["", "## Plants (use these ids in plant_id)"]
        for p in plants:
            from datetime import date as _date
            try:
                dt = (today - _date.fromisoformat(p["start_date"])).days if p.get("start_date") else None
            except ValueError:
                dt = None
            lines.append(f"- plant_id={p['id']}: \"{p['name']}\" owned by {p['owner'] or 'unknown'}; {p['strain']} ({p['breeder']}), {p['seed_type']}, {p['medium']}, {p['pot_size_l']:g} L; started {p.get('start_date') or 'unknown'}" + (f" → day {dt}" if dt is not None else "") + (f"; notes: {p['notes']}" if p.get("notes") else ""))
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
        paused = await self.controller.paused_until()
        if paused:
            lines.append(f"- Automation PAUSED until {paused}")
        if await self.controller.standby():
            lines.append("- TENT IN STANDBY: every device is off on purpose (nothing planted in it yet). Don't flag the environment as a problem; say what to prepare and when to start the tent.")

        lines += ["", "## Last 24 h"]
        lines.append(_summarise_readings(await self.store.readings_since(24), units))
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

    async def _parse(self, output_model: type[T], user_content: Any, settings: dict, history: list[dict] | None = None,
                     effort: str = "high", max_tokens: int = 16000) -> T:
        if not self.client:
            raise AdvisorError("Advisor is off: add your Anthropic API key in the add-on configuration.")
        model = settings.get("model") or self.default_model
        system = [
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": units_instruction(settings.get("units", "c"))},
        ]
        messages = list(history or []) + [{"role": "user", "content": user_content}]
        kwargs: dict[str, Any] = dict(
            model=model, max_tokens=max_tokens, system=system, messages=messages,
            output_format=output_model, output_config={"effort": effort},
        )
        try:
            try:
                resp = await self.client.beta.messages.parse(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except anthropic.BadRequestError as e:
                if "fallback" not in str(e).lower():
                    raise
                log.info("Server-side fallbacks not accepted here; retrying without them")
                resp = await self.client.beta.messages.parse(**kwargs)
        except anthropic.AuthenticationError:
            raise AdvisorError("Anthropic API key was rejected. Check it in the add-on configuration.")
        except anthropic.RateLimitError:
            raise AdvisorError("Claude is rate-limited right now. Try again in a minute.")
        except anthropic.APIStatusError as e:
            raise AdvisorError(f"Claude API error ({e.status_code}): {e.message}")
        except anthropic.APIConnectionError:
            raise AdvisorError("Could not reach the Claude API. Is the Home Assistant box online?")
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
        log.info("advisor %s: in=%s cached=%s out=%s", output_model.__name__, resp.usage.input_tokens,
                 getattr(resp.usage, "cache_read_input_tokens", 0), resp.usage.output_tokens)
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
        for tid in getattr(out, "tasks_done", []) or []:
            if tid in open_ids:
                await self.store.set_task_status(tid, "done")
                closed.append(tid)
        if closed:
            await self.store.add_event("info", "advisor", f"Advisor closed task(s) {', '.join('#' + str(t) for t in closed)}")
        open_titles = {(t.get("plant_id"), t["title"].strip().lower()) for t in open_tasks if t["id"] not in closed}
        for td in getattr(out, "tasks", []) or []:
            key = (pid_of(td), td.title.strip().lower())
            if key in open_titles:
                continue
            created_tasks.append(await self.store.add_task(td.title, td.detail, td.due, td.priority, "advisor", key[0]))
            open_titles.add(key)
        open_pr_titles = {(p.get("plant_id"), p["title"].strip().lower()) for p in await self.store.photo_requests("open")}
        for pd in getattr(out, "photo_requests", []) or []:
            key = (pid_of(pd), pd.title.strip().lower())
            if key in open_pr_titles:
                continue
            created_prs.append(await self.store.add_photo_request(pd.title, pd.instructions, pd.reason, key[0]))
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
                await self.notifier.send(f"photo_request:{pid}", f"The advisor would like {len(titles)} photo(s){who}: " + "; ".join(titles),
                                         title="Photo request", url="growop://photos", service=svc, everyone=svc is None)
        return {"tasks": created_tasks, "photo_requests": created_prs, "target_changes": applied_changes, "tasks_done": closed}

    async def _apply_target_changes(self, changes: list[TargetChange], settings: dict, source: str) -> list[dict]:
        targets, _, _ = await self.controller.effective_targets()
        override = await self.store.get_kv("targets_override", None) or {"values": {}, "source": "advisor"}
        values = dict(override.get("values", {}))
        out = []
        auto = bool(settings.get("auto_apply_advisor_targets", True))
        for ch in changes:
            if ch.field not in ADJUSTABLE_BY_ADVISOR:
                continue
            lo, hi = BOUNDS[ch.field]
            current = getattr(targets, ch.field)
            new = float(min(max(ch.to, lo), hi))
            # clamp the size of a single nudge
            limit = 2.0 if "temp" in ch.field else 5.0 if "humidity" in ch.field else 0.2
            new = max(current - limit, min(current + limit, new))
            new = round(new, 2 if "vpd" in ch.field else 1)
            rec = {"field": ch.field, "from": current, "to": new, "reason": ch.reason, "applied": auto}
            out.append(rec)
            if auto:
                values[ch.field] = new
        if auto and out:
            await self.store.set_kv("targets_override", {"values": values, "source": "advisor",
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
        out = await self._parse(BriefOut, content, settings, effort="high")
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
        out = await self._parse(LogAdviceOut, prompt, settings, effort="medium")
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
        out = await self._parse(PhotoAnalysisOut, content, settings, effort="high")
        applied = await self._apply(out, settings, "photo", default_plant_id=plant_id)
        analysis = out.model_dump()
        analysis.update(applied)
        await self.store.set_photo_analysis(photo_id, analysis)
        if request:
            await self.store.set_photo_request_status(request["id"], "done", photo_id)
        await self.store.add_event("info", "advisor", f"Photo analysed: health {out.health_score}/10 – {out.summary[:120]}")
        return analysis

    async def chat(self, message: str, plant_id: int | None = None) -> dict:
        ctx, settings = await self._context()
        history_rows = await self.store.chat_history(20)
        history = [{"role": r["role"], "content": r["content"]} for r in history_rows]
        plant = await self.store.get_plant(plant_id) if plant_id else None
        who = f"{plant['owner'] or 'Grower'} (about plant_id={plant['id']}, \"{plant['name']}\") says" if plant else "Grower says"
        # Fresh context goes into the latest user turn so the cached system prompt stays stable.
        user = f"<current_state>\n{ctx}\n</current_state>\n\n{who}: {message}"
        await self.store.add_chat("user", (f"[{plant['owner'] or plant['name']}] " if plant else "") + message)
        out = await self._parse(ChatOut, user, settings, history=history, effort="medium")
        applied = await self._apply(out, settings, "chat", default_plant_id=plant_id)
        reply = out.reply
        extras = []
        if applied["tasks"]:
            extras.append("Added task(s): " + "; ".join(t["title"] for t in applied["tasks"]))
        if applied["photo_requests"]:
            extras.append("Photo request(s) added in the Photos tab: " + "; ".join(p["title"] for p in applied["photo_requests"]))
        if applied["target_changes"]:
            extras.append("Targets adjusted: " + "; ".join(f"{c['field']} → {c['to']}" for c in applied["target_changes"] if c["applied"]))
        if extras:
            reply += "\n\n" + "\n".join(extras)
        mid = await self.store.add_chat("assistant", reply)
        return {"id": mid, "reply": reply}


# ---------------------------------------------------------------------- helpers

def _summarise_readings(rows: list[dict], units: str, short: bool = False) -> str:
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
