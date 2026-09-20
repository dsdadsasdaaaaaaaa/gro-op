# Grow Brain add-on

Automates a grow tent through the smart plugs and sensor you already have in Home Assistant,
and uses Claude as a grow advisor (daily brief, photo analysis, "I logged pH 6.8, what now?").

## Options

| Option | Meaning |
|---|---|
| `api_key` | Password the GrowOp iPhone app uses to talk to this add-on. Pick anything. If left empty a random one is generated and printed in the add-on log. |
| `anthropic_api_key` | Your Claude API key from console.anthropic.com. Without it the automation still runs, but the advisor features are off. |
| `model` | Claude model id. Default `claude-opus-5`. |
| `timezone` | e.g. `America/New_York`. Leave empty to use Home Assistant's timezone. Can also be set in the app. |
| `log_level` | `debug` / `info` / `warning` / `error`. |

## After starting

1. Open the GrowOp app → Settings → Server: URL `http://homeassistant.local:8099`, key = `api_key`.
2. Settings → Devices → "Auto-map from names", then check every role.
3. Settings → Grow: set the start date and stage.
4. That's it. The add-on now controls the tent. Check the Home tab.
