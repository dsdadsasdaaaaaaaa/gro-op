# Grow Op

A fully automated grow tent for one plant (Liberty Haze, Barney's Farm), run by your Home Assistant box,
with a Claude-powered grow advisor and a native iPhone app so the only things you do by hand are the
things a human has to do: water, feed, take a photo when asked, duct the exhaust.

```
 iPhone (GrowOp app)  ──HTTP──▶  Grow Brain (HA add-on, port 8099)  ──HA API──▶  smart plugs + sensor
                                     │  control loop every 30 s
                                     │  daily brief / photo analysis / "what next?"  ──▶ Claude API
```

Two parts:

| Part | Where it runs | What it does |
|---|---|---|
| `grow_brain/` | On your Home Assistant server as an **add-on** (or as a Docker container) | Reads the tent sensor, switches light / exhaust / fans / humidifier / dehumidifier / heater / AC toward stage-based targets with hysteresis and hard safety limits. Talks to Claude for the daily brief, photo requests + analysis, and advice whenever you log something (pH, EC, watering...). Sends push notifications through the HA companion app. |
| `ios/` | Your iPhone (build once in Xcode) | Big simple dashboard, advisor chat + daily brief, one-tap logging, photo requests with "stand here, light off, flash on" instructions, to-do list, settings. |

## What the automation does on its own

* **Light**: 18/6 in seedling/veg, 12/12 in flower, off while drying. Lights-on time is configurable (default 06:00).
* **Exhaust (+ intake)**: on when temperature or humidity is above target, plus a 5-minute fresh-air exchange every 20 minutes while lights are on. Off when the tent is too cold (keeps heat in).
* **Circulation fans**: always on.
* **Humidifier / dehumidifier / heater / AC**: pushed toward the stage target band with hysteresis and a minimum time between switches (3 min; 5 min for compressors). Only devices you actually have are used.
* **Day vs night bands**: the temperature band drops ~3 °C while lights are off.
* **Safety** (overrides everything, including manual overrides and "pause"): ≥ 35 °C → lights off, exhaust on; ≤ 12 °C → heater on; ≥ 85 % RH → exhaust + dehumidifier on; sensor stale for 30 min → safe mode (exhaust on, climate devices off), and you get a push notification.
* **Targets** come from the stage (seedling → veg → early/mid/late flower → flush → drying). Claude can nudge temperature/humidity/VPD targets within safe bounds (≤ 2 °C, ≤ 5 % RH, ≤ 0.2 kPa per change); you can edit them or reset to defaults in the app. Light schedule changes are never automatic.

The exhaust not being ducted outside the tent yet is recorded in the grow profile ("Exhaust is vented outside the tent" toggle, off by default). The controller still uses it for heat/humidity (limited effect), and the advisor knows and will tell you when it matters.

## Install: Home Assistant OS / Supervised (recommended)

1. Get this folder onto your HA box's `addons` share. Easiest: install the **Samba share** add-on, open `\\homeassistant\addons` (Mac: Finder → Go → Connect to Server → `smb://homeassistant.local/addons`), and copy the `grow_brain` folder in.
   (Or add `https://github.com/dsdadsasdaaaaaaaa/gro-op` under *Settings → Add-ons → Add-on store → ⋮ → Repositories*.)
2. *Settings → Add-ons → Add-on store → ⋮ → Check for updates*. "Grow Brain" appears under **Local add-ons**. Install it.
3. **Configuration** tab:
   * `api_key`: any password you like. You'll type it into the app.
   * `anthropic_api_key`: from https://console.anthropic.com → API keys.
   * `timezone`: e.g. `America/New_York`.
4. **Start** it, then look at the **Log** tab. You should see `Home Assistant reachable` and no errors.

## Install: Home Assistant Container / Core (Docker)

```bash
cp .env.example .env   # fill in HA_URL, a long-lived HA token (your profile page → Security), keys
docker compose up -d --build
```

## The iPhone app

1. Open `ios/GrowOp.xcodeproj` in Xcode, select the GrowOp target → *Signing & Capabilities* → pick your personal team.
2. Plug in your iPhone, choose it as the run destination, press ▶. (Free Apple ID works; the app needs re-signing every 7 days unless you have a paid developer account.)
3. First launch: URL `http://homeassistant.local:8099` (or `http://<HA-IP>:8099`), key = the `api_key` you chose. Connect.
4. **Settings → Devices → Auto-map from names**, then check each role. Everything in HA that looks like "Grow Light", "Exhaust Fan", "Tent Temperature" etc. is matched by name; fix anything it got wrong.
5. **Settings → Grow**: set the start date and current stage.
6. **Settings → Preferences**: pick your phone under *Notifications* so briefs, photo requests and alerts arrive as HA push notifications.

Away from home, the app only works over VPN (Tailscale / WireGuard add-on) since the API is plain HTTP on your LAN. That's on purpose.

## Day to day

* **Home** – is everything green? Temperature / humidity / VPD with targets, lights countdown, every device with the reason it's on or off. Tap a device to force it on/off for an hour, or pause automation while you work in the tent.
* **Advisor** – the morning brief (default 08:00) and a chat. "Should I flip to flower?", "leaves look droopy", "how much should I water?".
* **Log** – tap pH / EC / Watered / Fed / Height / Note, enter the number, and the advisor tells you what it means and what to do next.
* **Photos** – when the advisor wants to see something, it posts a request with exact instructions. Take the photo, send it, get a health score and findings.
* **Tasks** – what you have to do, from the advisor and from you.

## Developing / testing without a tent

```bash
python3 -m venv .venv && .venv/bin/pip install -r grow_brain/requirements.txt pytest pytest-asyncio
cd grow_brain && ../.venv/bin/python -m pytest -q          # unit tests (control logic, advisor plumbing with stubbed Claude)
../.venv/bin/python -m grow_brain.mock_ha &                # fake Home Assistant with a simulated tent on :8123
HA_URL=http://127.0.0.1:8123 HA_TOKEN=x GROW_API_KEY=test DATA_DIR=./data ../.venv/bin/python -m grow_brain.main
```
Then point the app (in the iOS Simulator) at `http://127.0.0.1:8099` with key `test`.

The full HTTP contract between app and add-on is in [docs/API.md](docs/API.md).

## Claude usage and cost

Model defaults to `claude-opus-5` (change in the add-on config or app settings). A typical day is one brief plus whatever you log or photograph: a few calls, each roughly 5–10k input tokens (system prompt is cached) and a few hundred output tokens. Photo analyses cost the most. Refusal fallbacks are enabled server-side, so an occasional safety decline is retried on another model automatically.
