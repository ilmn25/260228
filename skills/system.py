"""System utilities."""

import asyncio
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+
from pathlib import Path
from dotenv import load_dotenv

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

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

ALLOWED_ENV_VARS = {
    "DISCORD_USER_ID": "Discord user ID for the bot owner",
    "DISCORD_ACTIVATION_WORD": "Word/phrase used to activate the Discord bot session",
    "DEFAULT_TIMEZONE": "Default timezone to use for time calculations (e.g. UTC or America/New_York)",
    "GOOGLE_DEFAULT_EMAIL": "Default email account to use for Gmail and Calendar operations",
}

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
    """Update an environment variable in the .env file.
    
    Allowed environment variables:
    - DISCORD_USER_ID: Discord user ID for the bot owner
    - DISCORD_ACTIVATION_WORD: Word/phrase used to activate the Discord bot session
    
    Args:
        field: The environment variable name (must be from the allowed list)
        content: The value to set
    """
    if field not in ALLOWED_ENV_VARS:
        raise ValueError(f"Field '{field}' is not allowed. Allowed fields: {', '.join(ALLOWED_ENV_VARS.keys())}")

    _set_env_field(field, content)
    
    await ctx.info(f"Updated {field} in {ENV_FILE}")
    return {"status": "updated", "field": field, "file": ENV_FILE}


# OAuth token handling was moved to `skills/google_auth.py`. Import and call
# `google_auth.add_oauth_token` for similar functionality.
