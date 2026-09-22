"""SQLite persistence (aiosqlite). One small file in the data dir holds everything."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS device_map (role TEXT PRIMARY KEY, entity_id TEXT);
CREATE TABLE IF NOT EXISTS overrides (role TEXT PRIMARY KEY, mode TEXT NOT NULL, until TEXT);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, t TEXT NOT NULL,
    temp_c REAL, humidity REAL, vpd_kpa REAL, co2 REAL, light_on INTEGER
);
CREATE INDEX IF NOT EXISTS readings_t ON readings(t);
CREATE TABLE IF NOT EXISTS device_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, t TEXT NOT NULL, role TEXT NOT NULL, state TEXT NOT NULL, reason TEXT
);
CREATE INDEX IF NOT EXISTS device_log_t ON device_log(t);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, kind TEXT NOT NULL,
    value REAL, unit TEXT, context TEXT, note TEXT, advice_json TEXT
);
CREATE TABLE IF NOT EXISTS photo_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, title TEXT NOT NULL,
    instructions TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', photo_id INTEGER
);
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, request_id INTEGER, note TEXT,
    path TEXT NOT NULL, analysis_json TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, detail TEXT, due TEXT,
    priority TEXT NOT NULL DEFAULT 'normal', status TEXT NOT NULL DEFAULT 'open',
    created_by TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, json TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS camera_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT, t TEXT NOT NULL, path TEXT NOT NULL, lights_on INTEGER
);
CREATE INDEX IF NOT EXISTS camera_frames_t ON camera_frames(t);
CREATE TABLE IF NOT EXISTS plants (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, owner TEXT NOT NULL DEFAULT '',
    strain TEXT NOT NULL DEFAULT 'Liberty Haze', breeder TEXT NOT NULL DEFAULT "Barney's Farm",
    seed_type TEXT NOT NULL DEFAULT 'feminized photoperiod', medium TEXT NOT NULL DEFAULT 'soil',
    pot_size_l REAL NOT NULL DEFAULT 11.0, start_date TEXT, notes TEXT NOT NULL DEFAULT '',
    notify_service TEXT, created_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0
);
"""

# Columns added after the first release; applied idempotently at open().
MIGRATIONS = [
    ("events", "resolved_at", "TEXT"),
    ("log_entries", "plant_id", "INTEGER"),
    ("photo_requests", "plant_id", "INTEGER"),
    ("photos", "plant_id", "INTEGER"),
    ("tasks", "plant_id", "INTEGER"),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(SCHEMA)
        for table, col, typ in MIGRATIONS:
            async with self.db.execute(f"PRAGMA table_info({table})") as cur:
                cols = {r[1] for r in await cur.fetchall()}
            if col not in cols:
                await self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.commit()

    # ---- camera frames ----
    async def add_frame(self, path: str, lights_on: bool | None) -> int:
        cur = await self.db.execute("INSERT INTO camera_frames(t, path, lights_on) VALUES(?,?,?)",
                                    (iso(utcnow()), path, None if lights_on is None else int(lights_on)))
        await self.db.commit()
        return cur.lastrowid

    async def latest_frame(self, lights_on: bool | None = None) -> dict | None:
        q = "SELECT * FROM camera_frames" + (" WHERE lights_on=1" if lights_on else "") + " ORDER BY id DESC LIMIT 1"
        async with self.db.execute(q) as cur:
            r = await cur.fetchone()
        return dict(r) if r else None

    async def get_frame(self, fid: int) -> dict | None:
        async with self.db.execute("SELECT * FROM camera_frames WHERE id=?", (fid,)) as cur:
            r = await cur.fetchone()
        return dict(r) if r else None

    async def frames(self, days: float = 7, limit: int = 2000) -> list[dict]:
        since = iso(utcnow() - timedelta(days=days))
        async with self.db.execute("SELECT id, t, lights_on FROM camera_frames WHERE t>=? ORDER BY id LIMIT ?", (since, limit)) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def frame_count(self) -> int:
        async with self.db.execute("SELECT COUNT(*) AS n FROM camera_frames") as cur:
            return (await cur.fetchone())["n"]

    async def prune_frames(self, keep_days: int, frames_dir) -> None:
        cutoff = iso(utcnow() - timedelta(days=keep_days))
        async with self.db.execute("SELECT id, path FROM camera_frames WHERE t<?", (cutoff,)) as cur:
            old = await cur.fetchall()
        for r in old:
            try:
                Path(r["path"]).unlink(missing_ok=True)
            except Exception:
                pass
        if old:
            await self.db.execute("DELETE FROM camera_frames WHERE t<?", (cutoff,))
            await self.db.commit()

    # ---- plants ----
    async def plants(self, include_archived: bool = False) -> list[dict]:
        q = "SELECT * FROM plants" + ("" if include_archived else " WHERE archived=0") + " ORDER BY id"
        async with self.db.execute(q) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_plant(self, pid: int) -> dict | None:
        async with self.db.execute("SELECT * FROM plants WHERE id=?", (pid,)) as cur:
            r = await cur.fetchone()
        return dict(r) if r else None

    async def add_plant(self, **f) -> dict:
        cols = ["name", "owner", "strain", "breeder", "seed_type", "medium", "pot_size_l", "start_date", "notes", "notify_service"]
        vals = {c: f[c] for c in cols if c in f and f[c] is not None}
        vals["created_at"] = iso(utcnow())
        keys = ", ".join(vals); marks = ", ".join("?" for _ in vals)
        cur = await self.db.execute(f"INSERT INTO plants({keys}) VALUES({marks})", tuple(vals.values()))
        await self.db.commit()
        return await self.get_plant(cur.lastrowid)

    async def update_plant(self, pid: int, **f) -> dict | None:
        cols = ["name", "owner", "strain", "breeder", "seed_type", "medium", "pot_size_l", "start_date", "notes", "notify_service"]
        sets = {c: f[c] for c in cols if c in f}
        if sets:
            assign = ", ".join(f"{k}=?" for k in sets)
            await self.db.execute(f"UPDATE plants SET {assign} WHERE id=?", (*sets.values(), pid))
            await self.db.commit()
        return await self.get_plant(pid)

    async def archive_plant(self, pid: int) -> None:
        await self.db.execute("UPDATE plants SET archived=1 WHERE id=?", (pid,))
        await self.db.commit()

    async def assign_orphans_to_plant(self, pid: int) -> None:
        """One-time migration: rows created before plants existed belong to the first plant."""
        for t in ("log_entries", "photo_requests", "photos"):
            await self.db.execute(f"UPDATE {t} SET plant_id=? WHERE plant_id IS NULL", (pid,))
        await self.db.commit()

    async def close(self) -> None:
        if self.db:
            await self.db.close()

    # ---- kv ----
    async def get_kv(self, key: str, default: Any = None) -> Any:
        async with self.db.execute("SELECT value FROM kv WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
        return json.loads(row["value"]) if row else default

    async def set_kv(self, key: str, value: Any) -> None:
        await self.db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (key, json.dumps(value)))
        await self.db.commit()

    async def del_kv(self, key: str) -> None:
        await self.db.execute("DELETE FROM kv WHERE key=?", (key,))
        await self.db.commit()

    # ---- device map / overrides ----
    async def get_device_map(self) -> dict[str, str]:
        async with self.db.execute("SELECT role, entity_id FROM device_map") as cur:
            return {r["role"]: r["entity_id"] for r in await cur.fetchall() if r["entity_id"]}

    async def set_device(self, role: str, entity_id: str | None) -> None:
        if entity_id:
            await self.db.execute("INSERT OR REPLACE INTO device_map(role, entity_id) VALUES(?, ?)", (role, entity_id))
        else:
            await self.db.execute("DELETE FROM device_map WHERE role=?", (role,))
        await self.db.commit()

    async def get_overrides(self) -> dict[str, dict]:
        async with self.db.execute("SELECT role, mode, until FROM overrides") as cur:
            rows = await cur.fetchall()
        out = {}
        now = utcnow()
        for r in rows:
            until = parse_iso(r["until"])
            if until and until < now:
                await self.db.execute("DELETE FROM overrides WHERE role=?", (r["role"],))
                continue
            out[r["role"]] = {"mode": r["mode"], "until": r["until"]}
        await self.db.commit()
        return out

    async def set_override(self, role: str, mode: str, minutes: int | None) -> None:
        if mode == "auto":
            await self.db.execute("DELETE FROM overrides WHERE role=?", (role,))
        else:
            until = iso(utcnow() + timedelta(minutes=minutes)) if minutes else None
            await self.db.execute("INSERT OR REPLACE INTO overrides(role, mode, until) VALUES(?, ?, ?)", (role, mode, until))
        await self.db.commit()

    # ---- readings ----
    async def add_reading(self, temp_c, humidity, vpd, co2, light_on: bool | None) -> None:
        await self.db.execute(
            "INSERT INTO readings(t, temp_c, humidity, vpd_kpa, co2, light_on) VALUES(?,?,?,?,?,?)",
            (iso(utcnow()), temp_c, humidity, vpd, co2, None if light_on is None else int(light_on)),
        )
        await self.db.commit()

    async def readings_since(self, hours: float) -> list[dict]:
        since = iso(utcnow() - timedelta(hours=hours))
        async with self.db.execute(
            "SELECT t, temp_c, humidity, vpd_kpa, co2, light_on FROM readings WHERE t>=? ORDER BY t", (since,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def prune(self, keep_days: int = 120) -> None:
        cutoff = iso(utcnow() - timedelta(days=keep_days))
        await self.db.execute("DELETE FROM readings WHERE t<?", (cutoff,))
        await self.db.execute("DELETE FROM device_log WHERE t<?", (cutoff,))
        await self.db.execute("DELETE FROM events WHERE at<?", (cutoff,))
        await self.db.commit()

    # ---- device log / events ----
    async def log_device(self, role: str, state: str, reason: str) -> None:
        await self.db.execute("INSERT INTO device_log(t, role, state, reason) VALUES(?,?,?,?)",
                              (iso(utcnow()), role, state, reason))
        await self.db.commit()

    async def device_log_since(self, hours: float) -> list[dict]:
        since = iso(utcnow() - timedelta(hours=hours))
        async with self.db.execute("SELECT t, role, state, reason FROM device_log WHERE t>=? ORDER BY t", (since,)) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def add_event(self, level: str, kind: str, message: str) -> int:
        cur = await self.db.execute("INSERT INTO events(at, level, kind, message) VALUES(?,?,?,?)",
                                    (iso(utcnow()), level, kind, message))
        await self.db.commit()
        return cur.lastrowid

    async def resolve_alerts(self, kind: str, message_prefix: str) -> int:
        """Mark open warn/alert events of one kind (matching a message prefix) as resolved, so they stop showing as alerts."""
        cur = await self.db.execute(
            "UPDATE events SET resolved_at=? WHERE resolved_at IS NULL AND level IN ('warn','alert') AND kind=? AND message LIKE ?",
            (iso(utcnow()), kind, message_prefix + "%"))
        await self.db.commit()
        return cur.rowcount

    async def events(self, limit: int = 50, min_level: str | None = None, hours: float | None = None) -> list[dict]:
        q = "SELECT id, at, level, kind, message, resolved_at FROM events"
        conds, args = [], []
        if min_level == "warn":
            conds.append("level IN ('warn','alert') AND resolved_at IS NULL")
        if hours:
            conds.append("at>=?")
            args.append(iso(utcnow() - timedelta(hours=hours)))
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        async with self.db.execute(q, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ---- log entries ----
    async def add_log_entry(self, kind, value, unit, context, note, plant_id: int | None = None) -> dict:
        now = iso(utcnow())
        cur = await self.db.execute(
            "INSERT INTO log_entries(created_at, kind, value, unit, context, note, plant_id) VALUES(?,?,?,?,?,?,?)",
            (now, kind, value, unit, context, note, plant_id))
        await self.db.commit()
        return await self.get_log_entry(cur.lastrowid)

    async def set_log_advice(self, entry_id: int, advice: dict) -> None:
        await self.db.execute("UPDATE log_entries SET advice_json=? WHERE id=?", (json.dumps(advice), entry_id))
        await self.db.commit()

    async def get_log_entry(self, entry_id: int) -> dict:
        async with self.db.execute("SELECT * FROM log_entries WHERE id=?", (entry_id,)) as cur:
            return self._log_row(await cur.fetchone())

    async def log_entries(self, limit: int = 50) -> list[dict]:
        async with self.db.execute("SELECT * FROM log_entries ORDER BY id DESC LIMIT ?", (limit,)) as cur:
            return [self._log_row(r) for r in await cur.fetchall()]

    @staticmethod
    def _log_row(r) -> dict:
        if r is None:
            return {}
        advice = json.loads(r["advice_json"]) if r["advice_json"] else None
        return {
            "id": r["id"], "created_at": r["created_at"], "kind": r["kind"], "value": r["value"],
            "unit": r["unit"], "context": r["context"], "note": r["note"], "plant_id": r["plant_id"],
            "advice_summary": advice.get("summary") if advice else None,
        }

    # ---- photo requests ----
    async def add_photo_request(self, title: str, instructions: str, reason: str, plant_id: int | None = None) -> dict:
        cur = await self.db.execute(
            "INSERT INTO photo_requests(created_at, title, instructions, reason, plant_id) VALUES(?,?,?,?,?)",
            (iso(utcnow()), title, instructions, reason, plant_id))
        await self.db.commit()
        return await self.get_photo_request(cur.lastrowid)

    async def get_photo_request(self, rid: int) -> dict | None:
        async with self.db.execute("SELECT * FROM photo_requests WHERE id=?", (rid,)) as cur:
            r = await cur.fetchone()
        return dict(r) if r else None

    async def photo_requests(self, status: str | None = "open", limit: int = 50) -> list[dict]:
        if status:
            q, args = "SELECT * FROM photo_requests WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)
        else:
            q, args = "SELECT * FROM photo_requests ORDER BY id DESC LIMIT ?", (limit,)
        async with self.db.execute(q, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def set_photo_request_status(self, rid: int, status: str, photo_id: int | None = None) -> None:
        await self.db.execute("UPDATE photo_requests SET status=?, photo_id=COALESCE(?, photo_id) WHERE id=?",
                              (status, photo_id, rid))
        await self.db.commit()

    # ---- photos ----
    async def add_photo(self, request_id: int | None, note: str | None, path: str, plant_id: int | None = None) -> int:
        cur = await self.db.execute("INSERT INTO photos(created_at, request_id, note, path, plant_id) VALUES(?,?,?,?,?)",
                                    (iso(utcnow()), request_id, note, path, plant_id))
        await self.db.commit()
        return cur.lastrowid

    async def set_photo_analysis(self, pid: int, analysis: dict) -> None:
        await self.db.execute("UPDATE photos SET analysis_json=? WHERE id=?", (json.dumps(analysis), pid))
        await self.db.commit()

    async def get_photo(self, pid: int) -> dict | None:
        async with self.db.execute("SELECT * FROM photos WHERE id=?", (pid,)) as cur:
            r = await cur.fetchone()
        return self._photo_row(r) if r else None

    async def photos(self, limit: int = 30) -> list[dict]:
        async with self.db.execute("SELECT * FROM photos ORDER BY id DESC LIMIT ?", (limit,)) as cur:
            return [self._photo_row(r) for r in await cur.fetchall()]

    @staticmethod
    def _photo_row(r) -> dict:
        return {
            "id": r["id"], "created_at": r["created_at"], "request_id": r["request_id"], "note": r["note"],
            "plant_id": r["plant_id"],
            "path": r["path"], "analysis": json.loads(r["analysis_json"]) if r["analysis_json"] else None,
            "image_url": f"/api/photos/{r['id']}/image",
        }

    # ---- tasks ----
    async def add_task(self, title, detail, due, priority, created_by, plant_id: int | None = None) -> dict:
        cur = await self.db.execute(
            "INSERT INTO tasks(title, detail, due, priority, created_by, created_at, plant_id) VALUES(?,?,?,?,?,?,?)",
            (title, detail, due, priority, created_by, iso(utcnow()), plant_id))
        await self.db.commit()
        return await self.get_task(cur.lastrowid)

    async def get_task(self, tid: int) -> dict | None:
        async with self.db.execute("SELECT * FROM tasks WHERE id=?", (tid,)) as cur:
            r = await cur.fetchone()
        return dict(r) if r else None

    async def tasks(self, status: str | None = "open", limit: int = 100) -> list[dict]:
        if status:
            q, args = "SELECT * FROM tasks WHERE status=? ORDER BY COALESCE(due, '9999'), id DESC LIMIT ?", (status, limit)
        else:
            q, args = "SELECT * FROM tasks ORDER BY status DESC, COALESCE(due,'9999'), id DESC LIMIT ?", (limit,)
        async with self.db.execute(q, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def set_task_status(self, tid: int, status: str) -> dict | None:
        await self.db.execute("UPDATE tasks SET status=?, completed_at=? WHERE id=?",
                              (status, iso(utcnow()) if status == "done" else None, tid))
        await self.db.commit()
        return await self.get_task(tid)

    # ---- briefs ----
    async def add_brief(self, data: dict) -> dict:
        now = iso(utcnow())
        cur = await self.db.execute("INSERT INTO briefs(created_at, json) VALUES(?,?)", (now, json.dumps(data)))
        await self.db.commit()
        return {"id": cur.lastrowid, "created_at": now, "read": False, **data}

    async def latest_brief(self) -> dict | None:
        async with self.db.execute("SELECT * FROM briefs ORDER BY id DESC LIMIT 1") as cur:
            r = await cur.fetchone()
        if not r:
            return None
        return {"id": r["id"], "created_at": r["created_at"], "read": bool(r["read"]), **json.loads(r["json"])}

    async def recent_briefs(self, n: int = 3) -> list[dict]:
        async with self.db.execute("SELECT * FROM briefs ORDER BY id DESC LIMIT ?", (n,)) as cur:
            rows = await cur.fetchall()
        return [{"id": r["id"], "created_at": r["created_at"], **json.loads(r["json"])} for r in rows]

    async def mark_brief_read(self, bid: int) -> None:
        await self.db.execute("UPDATE briefs SET read=1 WHERE id=?", (bid,))
        await self.db.commit()

    async def unread_brief(self) -> bool:
        async with self.db.execute("SELECT read FROM briefs ORDER BY id DESC LIMIT 1") as cur:
            r = await cur.fetchone()
        return bool(r) and not bool(r["read"])

    # ---- chat ----
    async def add_chat(self, role: str, content: str) -> int:
        cur = await self.db.execute("INSERT INTO chat(role, content, created_at) VALUES(?,?,?)",
                                    (role, content, iso(utcnow())))
        await self.db.commit()
        return cur.lastrowid

    async def chat_history(self, limit: int = 50) -> list[dict]:
        async with self.db.execute("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,)) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def clear_chat(self) -> None:
        await self.db.execute("DELETE FROM chat")
        await self.db.commit()
