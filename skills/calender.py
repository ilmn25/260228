"""MCP server exposing Google Calendar CRUD tools.

Provides CRUD operations for Google Calendar events through the Model Context Protocol.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache, wraps
from typing import Any, Literal

from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from pydantic import BaseModel, Field, model_validator

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CalendarError(RuntimeError):
    pass


def _default_timezone() -> str:
    return (
        os.environ.get("GOOGLE_CALENDAR_TIMEZONE")
        or os.environ.get("DEFAULT_TIMEZONE")
        or "UTC"
    )


def _require_timezone(value: str | None) -> str:
    tz = value or _default_timezone()
    if not tz:
        raise ValueError("Timezone information is required")
    return tz


def _normalize_boundary(moment: str, tz_override: str | None) -> dict[str, str]:
    moment = moment.strip()
    if len(moment) == 10 and moment.count("-") == 2:
        return {"date": moment}
    try:
        dt = datetime.fromisoformat(moment)
    except ValueError as exc:
        raise ValueError("Datetime must be ISO 8601") from exc

    final_tz = tz_override or _default_timezone() or "UTC"

    if dt.tzinfo is None:
        # Keep local clock time and let Google interpret it using explicit timeZone.
        payload: dict[str, str] = {"dateTime": dt.isoformat(timespec="seconds")}
        payload["timeZone"] = _require_timezone(final_tz)
        return payload

    # Offset-aware datetime: preserve offset in dateTime and include a timeZone hint.
    tz_name = dt.tzinfo.key if hasattr(dt.tzinfo, "key") else None
    payload = {"dateTime": dt.isoformat()}
    payload["timeZone"] = tz_name or _require_timezone(final_tz)
    return payload


class Attendee(BaseModel):
    email: str = Field(description="Attendee email address")
    optional: bool = Field(False, description="Mark attendee as optional")


class EventCreateInput(BaseModel):
    summary: str = Field(min_length=1, description="Event title")
    start_time: str = Field(min_length=1, description="Start datetime or date in ISO 8601")
    end_time: str = Field(min_length=1, description="End datetime or date in ISO 8601")
    timezone: str | None = Field(default=None)
    description: str | None = None
    location: str | None = None
    attendees: list[Attendee] | None = None
    conference_meeting: bool = Field(default=False)
    send_updates: Literal["all", "externalOnly", "none"] | None = None


class EventUpdateInput(BaseModel):
    event_id: str = Field(min_length=1, description="Google Calendar event ID")
    summary: str | None = Field(default=None, min_length=1)
    description: str | None = None
    location: str | None = None
    start_time: str | None = Field(default=None, min_length=1)
    end_time: str | None = Field(default=None, min_length=1)
    timezone: str | None = None
    attendees: list[Attendee] | None = None
    conference_meeting: bool | None = None
    send_updates: Literal["all", "externalOnly", "none"] | None = None

    @model_validator(mode='after')
    def validate_time_fields(self) -> 'EventUpdateInput':
        """Ensure that if start_time or end_time is provided, both must be provided."""
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Both start_time and end_time must be provided together")
        return self


class EventFilters(BaseModel):
    time_min: str | None = None
    time_max: str | None = None
    max_results: int = Field(default=10, ge=1, le=250)
    query: str | None = None
    single_events: bool = Field(default=True)
    order_by_start: bool = Field(default=True)


def _simplify_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id"),
        "status": event.get("status"),
        "summary": event.get("summary"),
        "description": event.get("description"),
        "location": event.get("location"),
        "start": event.get("start"),
        "end": event.get("end"),
        "hangoutLink": event.get("hangoutLink"),
        "htmlLink": event.get("htmlLink"),
        "created": event.get("created"),
        "updated": event.get("updated"),
        "attendees": event.get("attendees", []),
    }


@dataclass
class GoogleCalendarClient:
    calendar_id: str
    credentials: Credentials
    _service_cache: Any | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_env(cls) -> "GoogleCalendarClient":
        calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
        credentials = cls._load_credentials()
        return cls(calendar_id=calendar_id, credentials=credentials)

    @staticmethod
    def _load_credentials() -> Credentials:
        token_path = os.environ.get("GOOGLE_CALENDAR_TOKEN_FILE")
        service_account_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        creds: Credentials | None = None
        if token_path:
            creds = OAuthCredentials.from_authorized_user_file(token_path, SCOPES)
        elif service_account_path:
            creds = service_account.Credentials.from_service_account_file(
                service_account_path, scopes=SCOPES
            )
        else:
            raise CalendarError("No Google credentials configured.")
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    def _service(self):
        if self._service_cache is None:
            self._service_cache = build(
                "calendar", "v3", credentials=self.credentials, cache_discovery=False
            )
        return self._service_cache

    def _call_google(self, operation: str, request: Any, params: dict[str, Any] | None = None) -> Any:
        if params:
            print(
                f"[google-call] op={operation} params={json.dumps(params, default=str)}",
                file=sys.stderr,
                flush=True,
            )
        return request.execute()

    def list_events(self, filters: EventFilters) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "calendarId": self.calendar_id,
            "maxResults": filters.max_results,
            "singleEvents": filters.single_events,
        }
        params["timeMin"] = filters.time_min or _utcnow_iso()
        if filters.time_max:
            params["timeMax"] = filters.time_max
        if filters.query:
            params["q"] = filters.query
        if filters.order_by_start and filters.single_events:
            params["orderBy"] = "startTime"
        request = self._service().events().list(**params)
        events_result = self._call_google("events.list", request, params)
        return [_simplify_event(item) for item in events_result.get("items", [])]

    def create_event(self, payload: EventCreateInput) -> dict[str, Any]:
        body = self._build_event_body(payload)
        params: dict[str, Any] = {"calendarId": self.calendar_id, "body": body}
        if payload.send_updates:
            params["sendUpdates"] = payload.send_updates
        if body.get("conferenceData"):
            params["conferenceDataVersion"] = 1
        request = self._service().events().insert(**params)
        event = self._call_google("events.insert", request, params)
        return _simplify_event(event)

    def update_event(self, payload: EventUpdateInput) -> dict[str, Any]:
        get_request = self._service().events().get(
            calendarId=self.calendar_id, eventId=payload.event_id
        )
        event_resource = self._call_google("events.get", get_request)
        if payload.summary is not None:
            event_resource["summary"] = payload.summary
        if payload.description is not None:
            event_resource["description"] = payload.description
        if payload.location is not None:
            event_resource["location"] = payload.location
        if payload.start_time is not None:
            event_resource["start"] = _normalize_boundary(payload.start_time, payload.timezone)
        if payload.end_time is not None:
            event_resource["end"] = _normalize_boundary(payload.end_time, payload.timezone)
        if payload.attendees is not None:
            event_resource["attendees"] = [attendee.model_dump() for attendee in payload.attendees]
        if payload.conference_meeting is not None:
            conference_data = self._build_conference_data(payload.conference_meeting)
            if conference_data is None:
                event_resource.pop("conferenceData", None)
            else:
                event_resource["conferenceData"] = conference_data
        params: dict[str, Any] = {"calendarId": self.calendar_id, "eventId": payload.event_id, "body": event_resource}
        if payload.send_updates:
            params["sendUpdates"] = payload.send_updates
        if event_resource.get("conferenceData"):
            params["conferenceDataVersion"] = 1
        request = self._service().events().update(**params)
        event = self._call_google("events.update", request, params)
        return _simplify_event(event)

    def delete_event(self, event_id: str, send_updates: Literal["all", "externalOnly", "none"] | None = None) -> None:
        params = {"calendarId": self.calendar_id, "eventId": event_id}
        if send_updates:
            params["sendUpdates"] = send_updates
        self._call_google("events.delete", self._service().events().delete(**params))

    def get_event(self, event_id: str) -> dict[str, Any]:
        params = {"calendarId": self.calendar_id, "eventId": event_id}
        event = self._call_google("events.get", self._service().events().get(**params))
        return _simplify_event(event)

    def _build_event_body(self, payload: EventCreateInput) -> dict[str, Any]:
        body: dict[str, Any] = {
            "summary": payload.summary,
            "start": _normalize_boundary(payload.start_time, payload.timezone),
            "end": _normalize_boundary(payload.end_time, payload.timezone),
        }
        if payload.description:
            body["description"] = payload.description
        if payload.location:
            body["location"] = payload.location
        if payload.attendees:
            body["attendees"] = [attendee.model_dump() for attendee in payload.attendees]
        if payload.conference_meeting:
            body["conferenceData"] = self._build_conference_data(True)
        return body

    def _build_conference_data(self, enabled: bool) -> dict[str, Any] | None:
        if not enabled:
            return None
        return {"createRequest": {"conferenceSolutionKey": {"type": "hangoutsMeet"}, "requestId": os.urandom(8).hex()}}


@lru_cache(maxsize=1)
def get_client() -> GoogleCalendarClient:
    return GoogleCalendarClient.from_env()


mcp = FastMCP("Google Calendar MCP", instructions="Interact with Google Calendar using CRUD-style tools.", json_response=True)


@mcp.tool()
async def obtain_oauth_token(ctx: Context[ServerSession, None]) -> dict[str, str]:
    """Run an interactive OAuth flow using google.json and save token.json.
    
    Call this to authorize the agent for user account access via OAuth."""
    try:
        flow = InstalledAppFlow.from_client_secrets_file("google.json", SCOPES)
        creds = await asyncio.to_thread(flow.run_local_server, port=0)
        token_path = "token.json"
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        await ctx.info(f"Saved OAuth token to {token_path}")
        return {"token_file": token_path}
    except Exception as exc:
        raise CalendarError(f"Failed to obtain OAuth token: {exc}") from exc


def _handle_google_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HttpError as exc:
            status = getattr(exc.resp, "status", "unknown")
            content = exc.content.decode("utf-8", errors="replace") if getattr(exc, "content", None) else str(exc)
            raise CalendarError(f"Google API error (status={status}): {content}") from exc

    return wrapper


@mcp.tool()
@_handle_google_errors
async def list_events(
    ctx: Context[ServerSession, None],
    query: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10
) -> list[dict[str, Any]]:
    """List upcoming calendar events with optional time range and search filters.
    
    Args:
        query: Search query to filter events by summary/description
        time_min: Minimum time bound (ISO 8601 format)
        time_max: Maximum time bound (ISO 8601 format)
        max_results: Maximum number of events to return (default 10)
    """
    filters = EventFilters(query=query, time_min=time_min, time_max=time_max, max_results=max_results)
    client = get_client()
    events = await asyncio.to_thread(client.list_events, filters)
    await ctx.info(f"Fetched {len(events)} events from {client.calendar_id}.")
    return events


@mcp.tool()
@_handle_google_errors
async def create_event(
    ctx: Context[ServerSession, None],
    summary: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    timezone: str | None = None
) -> dict[str, Any]:
    """Create a new calendar event with the given summary, time, and optional details.
    
    Args:
        summary: Event title/summary
        start_time: Start datetime in ISO 8601 format (e.g., '2026-05-06T14:00:00')
        end_time: End datetime in ISO 8601 format
        description: Optional event description
        location: Optional event location
        timezone: Optional timezone (e.g., 'Asia/Hong_Kong')
    """
    payload = EventCreateInput(
        summary=summary,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
        timezone=timezone
    )
    client = get_client()
    event = await asyncio.to_thread(client.create_event, payload)
    await ctx.info(f"Created event {event.get('id')}")
    return event


@mcp.tool()
@_handle_google_errors
async def update_event(
    ctx: Context[ServerSession, None],
    event_id: str,
    summary: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
    location: str | None = None,
    timezone: str | None = None
) -> dict[str, Any]:
    """Update an existing calendar event by ID.
    
    Args:
        event_id: Google Calendar event ID (obtain via list_events)
        summary: New event title (optional)
        start_time: New start datetime in ISO 8601 format (optional, must provide with end_time)
        end_time: New end datetime in ISO 8601 format (optional, must provide with start_time)
        description: New event description (optional)
        location: New event location (optional)
        timezone: Timezone for the times (optional)
    """
    payload = EventUpdateInput(
        event_id=event_id,
        summary=summary,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
        timezone=timezone
    )
    client = get_client()
    event = await asyncio.to_thread(client.update_event, payload)
    await ctx.info(f"Updated event {event_id}")
    return event


@mcp.tool()
@_handle_google_errors
async def delete_event(event_id: str, ctx: Context[ServerSession, None], send_updates: Literal["all", "externalOnly", "none"] | None = None,) -> dict[str, Any]:
    """Delete a calendar event by ID. Optionally notify attendees of the cancellation.
    
    The event_id can be obtained by calling list_events first to retrieve the 'id' field from returned events."""
    client = get_client()
    await asyncio.to_thread(client.delete_event, event_id, send_updates)
    await ctx.info(f"Deleted event {event_id}")
    return {"status": "deleted", "event_id": event_id}


@mcp.tool()
@_handle_google_errors
async def get_event(event_id: str, ctx: Context[ServerSession, None]) -> dict[str, Any]:
    """Fetch full details of a specific calendar event by ID.
    
    The event_id can be obtained by calling list_events first to retrieve the 'id' field from returned events."""
    client = get_client()
    event = await asyncio.to_thread(client.get_event, event_id)
    await ctx.info(f"Retrieved event {event_id}")
    return event


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
