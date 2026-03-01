"""Miscellaneous utilities exposed via MCP tools."""

from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

mcp = FastMCP("Miscellaneous MCP", instructions="Utility tools", json_response=True)

# Resolve .env path relative to this script's location
ENV_FILE = Path(__file__).parent.parent / ".env"
 
@mcp.tool()
async def get_time(ctx: Context[ServerSession, None]) -> dict[str, str]:
    """Return the current UTC time in ISO 8601 format."""
    now = datetime.now(timezone.utc).isoformat()
    await ctx.info(f"Current time is {now}")
    return {"utc_time": now}

ALLOWED_ENV_VARS = {
    "DISCORD_USER_ID": "Discord user ID for the bot owner",
    "DISCORD_ACTIVATION_WORD": "Word/phrase used to activate the Discord bot session",
}


def _normalize_env_value(value: str) -> str:
    cleaned = value.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        return cleaned[1:-1].strip()
    return cleaned


def _read_env_vars(env_path: Path) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars


def _write_env_vars(env_path: Path, env_vars: dict[str, str]) -> None:
    with open(env_path, "w", encoding="utf-8") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")


def _set_env_field(field: str, content: str) -> str:
    cleaned_value = _normalize_env_value(content)
    env_vars = _read_env_vars(ENV_FILE)
    env_vars[field] = cleaned_value
    _write_env_vars(ENV_FILE, env_vars)
    return cleaned_value

@mcp.tool()
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

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
