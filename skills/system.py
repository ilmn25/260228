"""System utilities."""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+
from pathlib import Path
from dotenv import load_dotenv

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from runtime_state import set_speech_enabled

# Resolve .env path relative to this script's location
ENV_FILE = Path(__file__).parent.parent / ".env"

# Load environment variables from .env file
load_dotenv(ENV_FILE)
 
def _get_default_timezone() -> str:
    """Read DEFAULT_TIMEZONE from the environment, falling back to UTC."""
    return os.getenv("DEFAULT_TIMEZONE", "UTC")

async def get_time(ctx: Context[ServerSession, None]) -> dict[str, str]:
    """Return the current time in the user's timezone.
    """
    tzname = _get_default_timezone()
    try:
        tz = ZoneInfo(tzname)
    except Exception:
        tz = timezone.utc
        tzname = "UTC"
    now = datetime.now(tz).isoformat()
    await ctx.info(f"Current time in {tzname} is {now}")
    return {"timezone": tzname, "time": now}


def _normalize_env_value(value: str) -> str:
    cleaned = value.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        return cleaned[1:-1].strip()
    return cleaned


def _set_env_field(field: str, content: str) -> str:
    from dotenv import set_key
    cleaned_value = _normalize_env_value(content)
    set_key(ENV_FILE, field, cleaned_value)
    return cleaned_value


async def edit_env(ctx: Context[ServerSession, None], field: str, content: str) -> dict[str, str]:
    """Set an existing variable in the `.env` file.

    Only keys that are already defined may be changed, run list_env tool first to see existing keys. 

    Args:
        field: name of the variable to set (must already exist in `.env`)
        content: value to assign to the variable
    """
    # read existing keys from file
    from dotenv import dotenv_values

    existing = set(dotenv_values(ENV_FILE).keys())
    if field not in existing:
        raise ValueError(
            f"Field '{field}' is not currently defined in {ENV_FILE}. "
            "Add it manually or choose an existing key to avoid typos."
        )

    _set_env_field(field, content)

    await ctx.info(f"Updated {field} in {ENV_FILE}")
    return {"status": "updated", "field": field, "file": ENV_FILE}


async def list_env(ctx: Context[ServerSession, None]) -> dict[str, list[str]]:
    """Return the names of variables in the `.env` file.

    Only keys are returned; values are omitted to avoid exposing secrets.
    """
    from dotenv import dotenv_values

    vars = dict(dotenv_values(ENV_FILE))
    keys = list(vars.keys())
    await ctx.info(f"Found {len(keys)} variables in {ENV_FILE}")
    return {"keys": keys}


async def set_speech_mode(ctx: Context[ServerSession, None], enabled: bool) -> dict[str, str]:
    """Enable or disable speech input at runtime.

    This updates shared runtime state used by the speech listener loop.

    Args:
        enabled: True to accept speech input, False to ignore speech input.
    """
    current = set_speech_enabled(enabled)
    value = "true" if current else "false"
    await ctx.info(f"Runtime speech input set to enabled={value}")
    return {"status": "updated", "field": "speech_enabled", "value": value}


