"""Google authentication utilities.

Includes OAuth token flow and helpers for managing authorized accounts.
"""

import asyncio
import os
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

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


async def add_oauth_token(
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


async def list_authed_emails(ctx: Context[ServerSession, None]) -> dict[str, list[str]]:
    """Return the list of email addresses that have OAuth tokens stored.

    The tokens are read from the same file used by :func:`add_oauth_token`.
    If the file does not exist, an empty list is returned.

    Args:
        ctx: unused context parameter.

    Returns:
        A dictionary containing a single key `emails` whose value is the list of
        authorized account email addresses.
    """
    # Determine token file location (mirrors logic in add_oauth_token)
    token_env = os.environ.get("GOOGLE_TOKEN_FILE")
    if token_env:
        token_path = Path(token_env)
    else:
        token_path = Path(__file__).parent.parent / "env" / "token.json"

    emails: list[str] = []
    if token_path.exists():
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                emails = list(data.keys())
        except Exception:
            # ignore parse errors, return empty list
            emails = []

    await ctx.info(f"Found {len(emails)} authorized email(s)")
    return {"emails": emails}
