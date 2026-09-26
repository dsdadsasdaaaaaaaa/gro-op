# Grow Brain HTTP API (contract for the iOS and Android apps and the web dashboard)

Base URL: `http://<home-assistant-host>:8099` (configurable in the app).
Every request except `GET /api/health` must carry the header `X-API-Key: <key>`.
All timestamps are ISO-8601 UTC strings. All temperatures are returned in BOTH °C and °F where noted; the app picks based on settings.

Errors: non-2xx with JSON `{"detail": "human readable message"}`.

## GET /api/health   (no auth)
`{"ok": true, "version": "0.9.4", "ha_connected": true, "advisor_enabled": true, "control": "ok", "last_cycle_at": "...", "consecutive_failures": 0}`.
Returns **503** with `ok:false` when the control loop has stopped or is stuck (used by the Supervisor watchdog; turn the add-on's Watchdog toggle on).

## GET /api/status
The single call that drives the dashboard.
```json
{
  "time": "2026-09-20T13:00:00Z",
  "ha_connected": true,
  "sensor": {
    "temp_c": 25.4, "temp_f": 77.7, "humidity": 58.2, "vpd_kpa": 1.05,
    "updated_at": "2026-09-20T12:59:30Z", "stale": false
  },
  "grow": { ...GrowProfile (see below)..., "day_in_stage": 12, "day_total": 26, "expected_harvest_date": "2026-11-20" },
  "targets": {
    "temp_min_c": 22.0, "temp_max_c": 28.0, "temp_min_f": 71.6, "temp_max_f": 82.4,
    "humidity_min": 55.0, "humidity_max": 65.0,
    "vpd_min": 0.8, "vpd_max": 1.2,
    "light_on_time": "06:00", "light_hours": 18,
    "source": "stage_default" | "advisor" | "manual",
    "note": "Veg defaults for Liberty Haze"
  },
  "light": { "is_on": true, "next_change_at": "2026-09-21T00:00:00Z", "schedule": "18/6" },
  "devices": [ DeviceStatus, ... ],
  "assessment": {
    "level": "good" | "warn" | "alert",
    "headline": "Everything on target",
    "details": ["Temp 25.4°C in range 22–28", "RH 58% in range 55–65"]
  },
  "open_tasks": 2,
  "open_photo_requests": 1,
  "unread_brief": true,
  "alerts": [ {"id": 1, "level": "warn", "message": "Humidity 72% above max 65%", "at": "..."} ]
}
```

### DeviceStatus
```json
{
  "role": "exhaust_fan",
  "label": "Exhaust fan",
  "kind": "switch",                       // "switch" | "sensor"
  "entity_id": "switch.grow_exhaust",     // null if unmapped
  "state": "on",                          // "on" | "off" | "unknown" | (sensor value as string)
  "mode": "auto",                         // "auto" | "on" | "off"  (manual override)
  "override_until": null,                 // ISO time or null
  "reason": "RH 68% > max 65%",           // why the controller has it in this state
  "available": true
}
```

### Device roles (fixed list)
| role | kind | required | label |
|---|---|---|---|
| light | switch | yes | Grow light |
| exhaust_fan | switch | yes | Exhaust fan |
| intake_fan | switch | no | Intake fan |
| circulation_fan | switch | no | Circulation fan |
| circulation_fan_2 | switch | no | Circulation fan 2 |
| humidifier | switch | no | Humidifier |
| dehumidifier | switch | no | Dehumidifier |
| heater | switch | no | Heater |
| cooler | switch | no | AC / cooler |
| temperature_sensor | sensor | yes | Temperature sensor |
| humidity_sensor | sensor | yes | Humidity sensor |
| vpd_sensor | sensor | no | VPD sensor (optional, computed if absent) |
| co2_sensor | sensor | no | CO2 sensor |

## GET /api/devices
```json
{ "devices": [DeviceStatus...], "roles": [ {"role":"light","label":"Grow light","kind":"switch","required":true,"description":"..."} ] }
```
## PUT /api/devices/{role}
Body `{"entity_id": "switch.grow_light"}` (or `{"entity_id": null}` to unmap). Returns DeviceStatus.
## POST /api/devices/{role}/override
Body `{"mode": "auto" | "on" | "off", "minutes": 60}` (minutes optional; omitted = until changed back to auto). Returns DeviceStatus.

## GET /api/ha/entities
Lists candidate Home Assistant entities for mapping.
```json
{"entities": [ {"entity_id":"switch.grow_light","name":"Grow Light","domain":"switch","state":"on","unit":null,"device_class":null,"suggested_role":"light"} ]}
```
## POST /api/ha/automap
Auto-assigns roles from entity names. Returns same shape as GET /api/devices.

## GET /api/grow   /   PUT /api/grow (partial update allowed)
GrowProfile:
```json
{
  "strain": "Liberty Haze", "breeder": "Barney's Farm", "seed_type": "feminized photoperiod",
  "medium": "soil",                 // "soil" | "coco" | "hydro" | "other"
  "pot_size_l": 11.0, "plant_count": 1,
  "start_date": "2026-08-25",       // date germinated / planted
  "stage": "veg",                   // "seedling" | "veg" | "flower" | "flush" | "drying" | "curing" | "done"
  "stage_started": "2026-09-08",
  "flower_start_date": null,
  "expected_flower_days": 65,
  "exhaust_ducted": false,          // exhaust not vented outside the tent yet
  "notes": ""
}
```
## POST /api/grow/stage   Body `{"stage": "flower"}` → GrowProfile (records date, resets targets to stage defaults, tells advisor).

## GET /api/targets → Targets (as in status)
## PUT /api/targets  Body: any subset of the numeric/time fields → Targets (source becomes "manual")
## DELETE /api/targets → resets to stage defaults

## GET /api/history?hours=24
```json
{"points": [ {"t":"...","temp_c":25.1,"temp_f":77.2,"humidity":60.2,"vpd_kpa":1.0,"light_on":true} ]}
```
Downsampled to ≤ 300 points.

## Logging what the human did / measured
### POST /api/log
```json
{"kind": "ph", "value": 6.8, "unit": "pH", "context": "runoff", "note": "after feeding"}
```
kinds: `ph`, `ec`, `ppm`, `water`, `feed`, `height`, `note`, `observation`, `defoliation`, `training`, `transplant`, `other`.
`value`/`unit`/`context`/`note` all optional. `context` free text (e.g. "water_in", "runoff", "reservoir").
Response (advice is generated by Claude synchronously; can take 10–40s):
```json
{
  "entry": LogEntry,
  "advice": {
    "summary": "6.8 runoff pH is on the high side of the soil range.",
    "steps": ["Next watering: pH the water to 6.2–6.4", "Re-test runoff next watering"],
    "urgency": "info" | "attention" | "urgent",
    "photo_requests": [PhotoRequest...],
    "tasks": [Task...]
  }
}
```
### GET /api/log?limit=50 → `{"entries": [LogEntry...]}`
LogEntry: `{"id":1,"created_at":"...","kind":"ph","value":6.8,"unit":"pH","context":"runoff","note":"...","advice_summary":"..."}`

## Photos
### GET /api/photo-requests?status=open → `{"requests": [PhotoRequest...]}`
PhotoRequest:
```json
{"id":3,"created_at":"...","title":"Top of canopy","instructions":"Stand directly above the plant...","reason":"To check for stretching","status":"open"|"done"|"skipped","photo_id":null}
```
### POST /api/photo-requests/{id}/skip
### POST /api/photos   multipart/form-data: `image` (jpeg/png), optional `request_id`, optional `note`
Analysis by Claude vision, synchronous (10–60s).
```json
{
  "id": 9, "created_at": "...", "request_id": 3, "note": "...",
  "analysis": {
    "summary": "...", "health_score": 8,
    "findings": [{"title":"Slight tip burn","severity":"info"|"warn"|"alert","detail":"..."}],
    "actions": ["..."],
    "photo_requests": [PhotoRequest...],
    "tasks": [Task...]
  },
  "image_url": "/api/photos/9/image"
}
```
### GET /api/photos?limit=30 → `{"photos": [Photo...]}`   (same shape, analysis included)
### GET /api/photos/{id}/image → image bytes (auth header required)
### GET /api/photos/{id}/thumb → small jpeg

## Tasks (to-do list for the human)
### GET /api/tasks?status=open → `{"tasks": [Task...]}`
Task: `{"id":4,"title":"Water with 1L pH 6.3","detail":"...","due":"2026-09-21","priority":"normal"|"high","status":"open"|"done","created_by":"advisor"|"user","created_at":"..."}`
### POST /api/tasks  Body `{"title":"...","detail":"...","due":"2026-09-21"}` → Task
### POST /api/tasks/{id}/complete → Task
### POST /api/tasks/{id}/reopen → Task

## Daily brief (the advisor's morning report)
### GET /api/brief → latest Brief or `null`
Brief:
```json
{"id":2,"created_at":"...","headline":"Day 26 — healthy, humidity creeping up","summary":"...",
 "concerns":["..."],"actions":["..."],
 "target_changes":[{"field":"humidity_max","from":65,"to":60,"reason":"..."}],
 "photo_requests":[PhotoRequest...],"tasks":[Task...],"read":false}
```
### POST /api/brief/run → Brief (generates now; 20–60s)
### POST /api/brief/{id}/read

## Chat with the advisor
### POST /api/chat  Body `{"message":"..."}` → `{"id": 12, "reply": "..."}`  (10–60s)
### GET /api/chat?limit=50 → `{"messages":[{"id":1,"role":"user"|"assistant","content":"...","created_at":"..."}]}`
### DELETE /api/chat → clears history

## Events / alerts
### GET /api/events?limit=50 → `{"events":[{"id":1,"at":"...","level":"info"|"warn"|"alert","kind":"device"|"safety"|"advisor"|"system","message":"..."}]}`

## Settings
### GET /api/settings / PUT /api/settings (partial)
```json
{
  "units": "c" | "f",
  "brief_time": "08:00",
  "timezone": "America/New_York",
  "auto_apply_advisor_targets": true,
  "notify_service": "notify.mobile_app_levis_iphone",   // HA notify service used for push; null = off
  "notify_services_available": ["notify.mobile_app_levis_iphone"],
  "model": "claude-opus-5",
  "advisor_enabled": true,
  "safety_temp_max_c": 35.0, "safety_temp_min_c": 12.0,
  "control_interval_s": 30, "min_switch_interval_s": 180
}
```

## POST /api/control/pause  Body `{"minutes": 30}` — pauses automatic control (all devices left as-is). POST /api/control/resume (clears pause and standby, keeps overrides).
## POST /api/control/standby → `{"standby": true}` — tent off: every device switches off and stays off. `assessment.level` becomes `"standby"`, headline "Tent is off".
## POST /api/control/start → `{"standby": false}` — fully automatic again: clears standby, pause and all manual overrides.
Status includes `"control_paused_until": null | "..."` and `"standby": true|false`. `alerts[]` items carry `kind`; safety/device/climate/system problems stay listed until they clear themselves, advisor warnings for 24 h. Safety, sensor, plug and climate alerts are also pushed to every plant owner's phone.

Status also includes `"learned": {"humidifier_pts_per_min": 1.8, "exhaust_c_per_min": 0.3, "exchange_rh_drop_per_min": 2.3}` (0.6.0; the swap drop since 0.8.5): the controller runs the humidifier and the exhaust cooling in **pulses** sized to the deficit, waits five minutes for the slow tent sensor, and learns each device's strength from every pulse. Keys are absent until the first clean measurement.
## GET /api/plan → the grow roadmap (phases with status done/current/upcoming, dates, what/watch_for/environment).

## Plants (v0.2.0): two plants, two people, one shared tent
Plant: `{"id":1,"name":"Levi's plant","owner":"Levi","strain":"Liberty Haze","breeder":"Barney's Farm","seed_type":"feminized photoperiod","medium":"soil","pot_size_l":11.0,"start_date":"2026-09-19"|null,"notes":"","notify_service":"notify.mobile_app_iphone"|null,"day_total":1,"created_at":"..."}`
- `GET /api/plants` → `{"plants":[Plant...]}`; `POST /api/plants` (name, owner, optional strain/breeder/seed_type/medium/pot_size_l/start_date/notes/notify_service) → Plant; `PUT /api/plants/{id}` partial → Plant; `DELETE /api/plants/{id}` → `{"ok":true}` (archives).
- Status gains `"plants":[Plant...]`; `grow` is tent-level (stage, dates, exhaust_ducted).
- `GET /api/plan?plant_id=N` computes from that plant's start date and returns `plant_id`.
- LogEntry, PhotoRequest, Photo, Task carry `plant_id` (null = whole tent). `POST /api/log`, `POST /api/tasks`, `POST /api/photos` (form field) and `POST /api/chat` accept `plant_id`.
- Brief gains `per_plant: [{plant_id, name, headline, summary}]`.
- Photo requests notify the plant owner's `notify_service` (falls back to everyone); briefs and safety alerts go to everyone.

## Tent camera (v0.3.0): any Home Assistant camera entity (Wyze via Docker Wyze Bridge, Tapo, ...)
Status gains `"camera": null | {"entity_id":"camera.tent_cam","name":"Wyze Cam Man cave","available":true,"snapshot_url":"/api/camera/snapshot","stream_url":"/api/camera/stream","last_frame_at":"..."|null,"frame_count":12,"error":null|"..."}`.
- `GET /api/camera` → `{"camera": ..., "candidates":[{"entity_id","name","state","brand","model"}]}`; `PUT /api/camera {"entity_id": "camera.x" | null}` (null = off; auto-picks a camera named wyze/tent/grow when unset).
- `GET /api/camera/snapshot` → fresh JPEG (auth header required; poll every 1–3 s for a live-ish view).
- `GET /api/camera/stream` → MJPEG (`multipart/x-mixed-replace`) passthrough from Home Assistant.
- `GET /api/camera/frames?days=7` → `{"frames":[{"id","t","lights_on","url":"/api/camera/frames/{id}"}]}` — the timelapse (one frame every `settings.camera_capture_minutes`, default 30, kept 14 days). `GET /api/camera/frames/{id}` → JPEG.
- `POST /api/camera/analyse {"plant_id": int|null, "note": "..."|null}` → Photo (same shape as an upload): takes a live snapshot and runs the advisor on it ("look now"). 10–60 s.
- The daily brief automatically includes the latest lights-on frame; Brief gains `camera_frame_at`.
- Settings gain `camera_entity` and `camera_capture_minutes`.

## Dashboard additions (v0.4.0)
- `GET /api/history?hours=168&points=1500` → same shape; `points` (max 3000) controls downsampling; hours up to 720.
- `GET /api/devices/history?hours=168` → `{"events":[{"t":"...","role":"exhaust_fan","state":"on"|"off","reason":"..."}]}` (every switch made by the controller).
- DeviceStatus gains `"power_w": 118.2 | null` (live watts from the plug's power sensor when the plug has one).
- `GET /api/energy` → `{"devices":[{"role","label","power_w","today_kwh","month_kwh"}],"today_kwh":1.23,"month_kwh":12.5,"price_per_kwh":0.15|null,"currency":"CAD","today_cost":0.18|null,"month_cost":1.9|null}`.
- Settings gain `temp_offset_c` (added to the raw sensor reading), `humidity_offset`, `price_per_kwh`, `currency`.
- Power watchdog: a device that is ON for 3+ minutes but draws (almost) no power raises a warn event + notification ("Humidifier is on but not drawing power — tank empty or unplugged?"). Same for a light that should be on.
- `GET /api/backup` → `application/zip` of the database + photos (auth header).
- `GET /` serves the web dashboard (static files under `/assets/`). The dashboard sends `X-API-Key` on every call and loads images with fetch()+blob URLs (no key in URLs).

## Additions in 0.8.x
Every request may carry `X-Device-Id: <random id per phone/browser>`; it keeps the "unread brief" flag per phone.

**Status**
- `targets.band`: `"day"` or `"night"` (which band the numbers are right now); `day_targets`: the daytime band when it is night.
- `humidifier_tank`: `{"run_hours_since_refill","tank_hours","hours_left","percent_left","dry","refill_at","refill_task_id"}` (misting time since the last refill vs. `settings.humidifier_tank_hours`; `dry` once the plug stops drawing power while on).
- `exhaust_duty_1h`: share of the last hour the exhaust ran (0–1).
- `learned`: see 0.6.0 above. `alerts[]` are de-duplicated and self-clearing kinds drop after 7 days.
- DeviceStatus `mode` `"on"`/`"off"` means *set by hand*; `override_until` is when it returns to auto (null = until changed).

**Logging**
- `POST /api/log` gains `"advise": false` (default): the entry is saved instantly and free, and the reply says the next brief will read it. `"advise": true` asks the advisor now (10–40 s, paid). Kinds add `planted` (counts seedling days from here) and `transplant` (while still a seedling, adds the task "Switch the stage to Veg").
- LogEntry gains `advice_steps` and `urgency`. Ticking a task writes a `note` entry with `context: "task"` and `note: "Done: <title>"`.

**Tasks**
- `POST /api/tasks/{id}/complete` may add follow-ups. Every planting (a `planted` log entry, or ticking a "Plant … seed" task) and every "put the dome on" task schedules "Take the dome off <plant>" four days later, once per plant.
- Each daily camera check replaces the previous one's warning; a clean "look now" (`POST /api/camera/analyse`) clears it too.
- `POST /api/tasks/{id}/reopen` within 10 minutes of the tick (the apps' Undo) also removes that tick's "Done:" log line and any follow-up task it created that is still open.

**Chat**
- `POST /api/chat {"message","plant_id": int|null,"author": "Levi"|null}`: `author` is who is asking (the phone's owner); without it the plant's owner is assumed. `GET /api/chat` messages gain `author` (the asker, or "Advisor") and `plant_id`.

**Advisor records**
- Brief and chat replies may carry `plantings: [{"plant_id","kind": "planted"|"transplant","date"}]`: what the advisor recorded in the log from a conversation (dated the day it happened; a record of the same kind on another day is corrected, not doubled). The plan counts seedling days from these.
- Photo analyses (uploads, look-now, the daily camera check) may carry `sprouted: [plant_id]`: the first time a seedling is seen through the soil. The app logs a `sprouted` entry, pushes to both phones, re-dates that plant's "Take the dome off" reminder to 5 days later, and closes the daily sprout-check job once every plant is up. LogEntry kinds gain `sprouted`.

**Stages (0.9.3)**
- Stage targets are per phase and ease over 3 days (seedling 22–26 °C / 65–75 %; veg 60–70 % easing to 55–65 % after two weeks; flower 50–60 % → 45–52 % from day 21 → 40–48 % from day 49 with cooler nights; drying 16–20 °C / 55–62 %).
- `POST /api/grow/stage` also lays out that stage's dated jobs as system tasks (veg: topping, low-stress training, trellis net, the flip check; flower: lollipop, day-21 defoliation, trichome checks; flush; drying).

**Plants and notifications**
- `GET /api/plants?include_archived=true`; `POST /api/plants/{id}/restore` un-archives.
- `POST /api/notify/test?service=notify.mobile_app_x` sends a test push to that phone.
- `POST /api/humidifier/refilled` resets the tank estimate → the `humidifier_tank` object.

**Settings** (GET returns them all; PUT accepts any subset)
- `advisor_budget_usd` (default 40, 1–500): monthly cap on Claude spend; calls stop with a clear message when reached. `advisor_month_usd` is this month's spend.
- `models_available`: the models `model` may be set to.
- `humidifier_tank_hours` (default 4): hours of misting one tank lasts.
- `admin_notify_service`: the phone that gets "update the add-on" notices (default: the first plant's phone).

**Humidity and fresh air (0.8.5)**
- Fresh air comes in short swaps sized so each costs about 3 points of humidity (from the learned `exchange_rh_drop_per_min`), enough minutes per hour for the stage (seedling 3, later 15), at most three an hour, counted from the last time the exhaust ran for any reason, and never while fresh mist is still settling.
- The humidifier fills to an aim a few points inside the band (seedling/veg: minimum + the swap's dip + 1, at most a third of the way in; flower/flush/drying: minimum + 2), and refills straight after each swap, sized from the predicted (not the lagging) humidity.
- After each refill the add-on compares where the tent ended up with the aim and nudges the learned swap drop, so the refills size themselves to the tent.

