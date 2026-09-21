# Grow Brain HTTP API (contract for the iOS app)

Base URL: `http://<home-assistant-host>:8099` (configurable in the app).
Every request except `GET /api/health` must carry the header `X-API-Key: <key>`.
All timestamps are ISO-8601 UTC strings. All temperatures are returned in BOTH °C and °F where noted; the app picks based on settings.

Errors: non-2xx with JSON `{"detail": "human readable message"}`.

## GET /api/health   (no auth)
```json
{"ok": true, "version": "0.1.0", "ha_connected": true, "advisor_enabled": true}
```

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
Status includes `"control_paused_until": null | "..."` and `"standby": true|false`.
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
Status gains `"camera": null | {"entity_id":"camera.wyze_cam_man_cave","name":"Wyze Cam Man cave","available":true,"snapshot_url":"/api/camera/snapshot","stream_url":"/api/camera/stream","last_frame_at":"..."|null,"frame_count":12,"error":null|"..."}`.
- `GET /api/camera` → `{"camera": ..., "candidates":[{"entity_id","name","state","brand","model"}]}`; `PUT /api/camera {"entity_id": "camera.x" | null}` (null = off; auto-picks a camera named wyze/tent/grow when unset).
- `GET /api/camera/snapshot` → fresh JPEG (auth header required; poll every 1–3 s for a live-ish view).
- `GET /api/camera/stream` → MJPEG (`multipart/x-mixed-replace`) passthrough from Home Assistant.
- `GET /api/camera/frames?days=7` → `{"frames":[{"id","t","lights_on","url":"/api/camera/frames/{id}"}]}` — the timelapse (one frame every `settings.camera_capture_minutes`, default 30, kept 14 days). `GET /api/camera/frames/{id}` → JPEG.
- `POST /api/camera/analyse {"plant_id": int|null, "note": "..."|null}` → Photo (same shape as an upload): takes a live snapshot and runs the advisor on it ("look now"). 10–60 s.
- The daily brief automatically includes the latest lights-on frame; Brief gains `camera_frame_at`.
- Settings gain `camera_entity` and `camera_capture_minutes`.
