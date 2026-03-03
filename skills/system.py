"""System utilities."""

import asyncio
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+
from pathlib import Path
from dotenv import load_dotenv

from google_auth_oauthlib.flow import InstalledAppFlow
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


# Google OAuth scopes for different services
GOOGLE_SCOPES = {
    "calendar": [
        "https://www.googleapis.com/auth/calendar"
    ],
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify"
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file"
    ],
    "docs": [
        "https://www.googleapis.com/auth/documents"
    ],
    "sheets": [
        "https://www.googleapis.com/auth/spreadsheets"
    ],
    "tasks": [
        "https://www.googleapis.com/auth/tasks"
    ]
}


async def obtain_oauth_token(
    ctx: Context[ServerSession, None],
    services: str = "calendar,gmail",
    email: str = ""
) -> dict[str, str]:
    """Run an interactive OAuth flow using google.json and save token.json.
    
    This authorizes the agent for user account access to various Google services via OAuth.
    Supports multiple email accounts by storing tokens in a structured format.
    
    Args:
        services: Comma-separated list of Google services to authorize.
                  Available: calendar, gmail, drive, docs, sheets, tasks
                  Default: "calendar,gmail"
        email: Email account identifier. If empty, will use the authenticated email.
    
    Returns:
        Dictionary with token_file path and authorized services
    """
    try:
        # Parse requested services
        requested_services = [s.strip().lower() for s in services.split(",")]
        
        # Validate services
        invalid_services = [s for s in requested_services if s not in GOOGLE_SCOPES]
        if invalid_services:
            raise ValueError(
                f"Invalid services: {', '.join(invalid_services)}. "
                f"Available services: {', '.join(GOOGLE_SCOPES.keys())}"
            )
        
        # Collect all required scopes
        scopes = []
        for service in requested_services:
            scopes.extend(GOOGLE_SCOPES[service])
        
        # Remove duplicates while preserving order
        scopes = list(dict.fromkeys(scopes))
        
        # hard-coded location of the client secrets JSON
        google_json_path = Path(__file__).parent.parent / "env" / "google.json"
        if not google_json_path.exists():
            raise FileNotFoundError(
                "google.json not found at expected path: env/google.json"
            )
        
        # Run OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(str(google_json_path), scopes)
        creds = await asyncio.to_thread(flow.run_local_server, port=0)
        
        # Determine where to write the token; allow override via env var
        token_env = os.environ.get("GOOGLE_TOKEN_FILE")
        if token_env:
            token_path = Path(token_env)
            token_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            token_dir = Path(__file__).parent.parent / "env"
            token_dir.mkdir(exist_ok=True)
            token_path = token_dir / "token.json"

        # Get the email from credentials if not provided
        import json
        creds_dict = json.loads(creds.to_json())
        account_email = email
        
        # For OAuth tokens, we need to make an API call to get the email
        if not account_email:
            # Build Gmail service to get the user's email
            from googleapiclient.discovery import build
            gmail_service = build('gmail', 'v1', credentials=creds)
            profile = gmail_service.users().getProfile(userId='me').execute()
            account_email = profile.get('emailAddress')
            
            if not account_email:
                raise RuntimeError("Unable to determine email address from OAuth credentials")
        
        # Load existing tokens or create new structure (multi-email format only)
        tokens = {}
        if token_path.exists():
            try:
                with open(token_path, "r", encoding="utf-8") as f:
                    tokens = json.load(f)
            except (json.JSONDecodeError, KeyError):
                # If file is corrupted, start fresh
                tokens = {}
        
        # Add or update the token for this email
        tokens[account_email] = creds_dict
        
        # Save the updated tokens
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)

        await ctx.info(
            f"Successfully authorized for services: {', '.join(requested_services)}\n"
            f"Saved OAuth token for {account_email} to {token_path}"
        )

        return {
            "message": f"Successfully saved OAuth token for {account_email} to {token_path}",
            "services": ", ".join(requested_services)
        }
    except Exception as exc:
        raise RuntimeError(f"Failed to obtain OAuth token: {exc}") from exc
