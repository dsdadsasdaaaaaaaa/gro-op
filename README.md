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
| `ios/` | Your iPhone (build once in Xcode) |
| `android/` | An Android phone (install the APK from the GitHub release, or build with Gradle) | Big simple dashboard, advisor chat + daily brief, one-tap logging, photo requests with "stand here, light off, flash on" instructions, to-do list, settings. |

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

**Away from home (Nabu Casa or any remote HA URL):** in the app choose *Through Home Assistant* and enter your Home Assistant URL (e.g. `https://xxxx.ui.nabu.casa`), a Home Assistant long-lived access token (HA → your profile, bottom left → Security → *Create token*), and the Grow Brain `api_key`. The app then talks to the add-on through Home Assistant's add-on ingress, so nothing extra is exposed to the internet. On the same Wi-Fi, *Same Wi-Fi* mode with `http://homeassistant.local:8099` is faster.

### Android phone

The Android app is the same app on the same API. Easiest: on the phone, open the latest release on the GitHub repo and download `GrowOp.apk`, then open it (allow "install unknown apps" for your browser when asked). To build it yourself:

```bash
cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew assembleDebug
```
The APK lands in `android/app/build/outputs/apk/debug/`. First launch: same two connection modes as the iPhone app, then pick which plant is yours.

### TestFlight (optional)

If you have a paid Apple Developer membership, `ios/scripts/testflight.sh` archives the app and uploads it to TestFlight so it installs like a normal app and doesn't expire. Prerequisites are listed at the top of the script (sign into Xcode, create the app record in App Store Connect). Expo/EAS does not apply: this is a native Swift project.

## Web dashboard

The add-on serves its own dashboard (nothing to install): at home open `http://homeassistant.local:8099/` (or the HA box's IP) in any browser and enter the `api_key` once. Away from home, open the **Grow Brain** entry in the Home Assistant sidebar; it's the same page, reached through Home Assistant's remote link. Pages: Overview (tent, rings, 24 h charts, light bar, devices with watts, live camera and timelapse), History (24 h / 7 d / 30 d charts, device on/off timeline, energy and cost), Journal (per-plant timeline of logs, photos, requests, tasks, briefs), Advisor (brief and chat) and Settings (plants, tent, targets, camera, preferences, backup download).

## Hosted dashboard (Vercel)

`dashboard/` is the same web dashboard packaged for Vercel: static files plus one function (`api/index.js`) that proxies `/api/*` to the add-on through Home Assistant's remote link (add-on ingress via the WebSocket API). The site is protected by a dashboard password; the add-on's key and the HA token stay in Vercel environment variables (`HA_URL`, `HA_TOKEN`, `GROW_API_KEY`, `DASHBOARD_PASSWORD`). Deploy with `cd dashboard && ./sync-web.sh && vercel deploy --prod`. Live at your Vercel URL

## Day to day

* **Tent off / Start**: the big switch on Home. Standby switches every device off and keeps it off (an empty tent while seeds germinate); Start puts everything back on automatic and clears manual overrides.
* **Grow plan**: the roadmap card on Home opens a phase-by-phase timeline (germination → cup → veg → stretch → bulking → ripening → flush → dry → cure) with dates, what to do and what to watch for. The advisor follows the same plan.
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
