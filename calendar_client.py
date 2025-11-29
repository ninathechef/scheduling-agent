import datetime as dt
from datetime import datetime
import os
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CREDENTIALS_PATH = os.getenv("GOOGLE_CLIENT_SECRETS", os.path.join("secrets", "credentials.json"))
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
DEFAULT_CALENDAR_ID = os.getenv("MANAGED_CALENDAR_ID")

def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def list_upcoming_events(service: Any, calendar_id: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    selected_calendar_id = calendar_id or DEFAULT_CALENDAR_ID
    if not selected_calendar_id:
        raise ValueError("Calendar ID missing. Set MANAGED_CALENDAR_ID in your environment.")
    now = dt.datetime.utcnow().isoformat() + "Z"
    events_result = (
        service.events()
        .list(calendarId=selected_calendar_id, timeMin=now, maxResults=max_results, singleEvents=True, orderBy="startTime")
        .execute()
    )
    events = []
    for event in events_result.get("items", []):
        start = event.get("start", {})
        end = event.get("end", {})
        events.append({
            "id": event.get("id"),
            "summary": event.get("summary"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "location": event.get("location"),
            "htmlLink": event.get("htmlLink"),
        })
    return events

def create_event(
    service,
    calendar_id: str,
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    timezone: str = None,
):
    """Create a single event in the given calendar and return the created event."""
    if timezone is None:
        timezone = os.getenv("TIMEZONE", "Europe/Brussels")

    event_body = {
        "summary": summary,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": timezone,
        },
    }

    created = (
        service.events()
        .insert(calendarId=calendar_id, body=event_body)
        .execute()
    )
    return created