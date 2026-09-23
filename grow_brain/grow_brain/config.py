"""Boot-time configuration.

Runs in two modes:
  * Home Assistant add-on: options come from /data/options.json, HA is reached through
    the Supervisor proxy using SUPERVISOR_TOKEN.
  * Standalone (docker / bare python): options come from environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class BootConfig:
    data_dir: Path
    ha_url: str
    ha_token: str
    api_key: str
    anthropic_api_key: str | None
    model: str
    timezone: str
    port: int
    log_level: str
    in_addon: bool


def _read_options() -> dict:
    p = Path("/data/options.json")
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as e:  # pragma: no cover
            log.error("Could not parse %s: %s", p, e)
    return {}


def load_boot_config() -> BootConfig:
    opts = _read_options()
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    in_addon = bool(supervisor_token)

    if in_addon:
        ha_url = "http://supervisor/core"
        ha_token = supervisor_token or ""
    else:
        ha_url = (opts.get("ha_url") or os.environ.get("HA_URL") or "http://homeassistant.local:8123").rstrip("/")
        ha_token = opts.get("ha_token") or os.environ.get("HA_TOKEN") or ""

    data_dir = Path(os.environ.get("DATA_DIR") or ("/data" if (in_addon or opts) else "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    api_key = opts.get("api_key") or os.environ.get("GROW_API_KEY") or ""
    if not api_key:
        key_file = data_dir / "api_key.txt"
        if key_file.exists():
            api_key = key_file.read_text().strip()
        else:
            api_key = secrets.token_urlsafe(24)
            key_file.write_text(api_key)
        log.warning("No api_key configured. Using a generated key saved in %s (open the dashboard's "
                    "'Set up a phone' QR to use it).", key_file)

    anthropic_key = opts.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY") or None
    model = opts.get("model") or os.environ.get("GROW_MODEL") or "claude-opus-5"
    tz = opts.get("timezone") or os.environ.get("TZ") or "UTC"
    port = int(opts.get("port") or os.environ.get("PORT") or 8099)
    log_level = (opts.get("log_level") or os.environ.get("LOG_LEVEL") or "info").upper()

    return BootConfig(
        data_dir=data_dir,
        ha_url=ha_url,
        ha_token=ha_token,
        api_key=api_key,
        anthropic_api_key=anthropic_key,
        model=model,
        timezone=tz,
        port=port,
        log_level=log_level,
        in_addon=in_addon,
    )
