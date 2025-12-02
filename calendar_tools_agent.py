"""
Simple helper functions used by the calendar agent.
"""
from calendar_client import (
    get_calendar_service,
    list_upcoming_events,
    create_event,
    create_recurring_event,
    update_event,
    delete_event,
    freebusy_query,
)
import os
from datetime import datetime
from typing import List, Dict, Any
from zoneinfo import ZoneInfo
from agents import function_tool
from googleapiclient.errors import HttpError

# Force all time normalization to Europe/Brussels.
TIMEZONE = "Europe/Brussels"
MANAGED_CALENDAR_ID = os.getenv("MANAGED_CALENDAR_ID", "").strip()

@function_tool
def list_upcoming_events_tool(user_query: str, max_results: int = 5) -> str:
    """
    Returns a human-readable list of upcoming events.
    """
    service = get_calendar_service()
    calendar_id = os.getenv("MANAGED_CALENDAR_ID")
    events: List[Dict[str, Any]] = list_upcoming_events(
        service, calendar_id=calendar_id, max_results=max_results
    )

    if not events:
        return "No upcoming events found."

    lines = []
    for ev in events:
        lines.append(f"- {ev.get('summary', '(no title)')} | start: {ev.get('start')} | end: {ev.get('end')}")
    return "\n".join(lines)

@function_tool
def create_simple_event_tool(
    title: str,
    start_iso: str,
    end_iso: str,
    timezone: str | None = None,
) -> Dict[str, Any]:
    """
    Create a simple event in the managed calendar.

    Args:
        title: The title/summary of the event.
        start_iso: Start datetime in ISO format (e.g. '2025-12-01T09:00:00').
        end_iso: End datetime in ISO format (e.g. '2025-12-01T10:00:00').
        timezone: IANA timezone string, e.g. 'Europe/Brussels'. Defaults to TIMEZONE env.

    Returns:
        A simplified event dict with id, summary, start, and end.
    """
    if timezone is None:
        timezone = TIMEZONE

    service = get_calendar_service()
    start_dt = datetime.fromisoformat(start_iso)
    end_dt = datetime.fromisoformat(end_iso)

    created = create_event(service, MANAGED_CALENDAR_ID, title, start_dt, end_dt, timezone)
    return {
        "id": created.get("id"),
        "summary": created.get("summary"),
        "start": created.get("start"),
        "end": created.get("end"),
    }


@function_tool
def create_recurring_event_tool(
    title: str,
    first_start_iso: str,
    first_end_iso: str,
    rrule: str,
    location: str | None = None,
    timezone: str | None = None,
) -> Dict[str, Any]:
    """
    Create a recurring event in the managed calendar.

    Args:
        title: Event title/summary.
        first_start_iso: First occurrence start datetime (ISO 8601).
        first_end_iso: First occurrence end datetime (ISO 8601).
        rrule: RFC5545 RRULE string (e.g. 'RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=...').
        location: Optional location.
        timezone: Optional IANA timezone (defaults from env).

    Returns:
        Dict with id, summary, start, end, recurrence.
    """
    if timezone is None:
        timezone = TIMEZONE

    service = get_calendar_service()

    created = create_recurring_event(
        service,
        MANAGED_CALENDAR_ID,
        title,
        first_start_iso,
        first_end_iso,
        rrule,
        location=location,
        timezone=timezone,
    )

    return {
        "id": created.get("id"),
        "summary": created.get("summary"),
        "start": created.get("start"),
        "end": created.get("end"),
        "recurrence": created.get("recurrence"),
    }

@function_tool
def update_event_tool(
    event_title: str | None = None,
    event_id: str | None = None,
    new_title: str | None = None,
    new_start_iso: str | None = None,
    new_end_iso: str | None = None,
    timezone: str | None = None,
) -> Dict[str, Any]:
    """
    Update an existing event in the managed calendar.

    Args:
        event_title: Title query to locate the event (used if event_id not provided).
        event_id: The Google Calendar event ID to update (preferred when known).
        new_title: Optional new title/summary.
        new_start_iso: Optional new start datetime in ISO format.
        new_end_iso: Optional new end datetime in ISO format.
        timezone: Optional IANA timezone (defaults to TIMEZONE env).

    Returns:
        The updated event as a simplified dict.
    """
    if timezone is None:
        timezone = TIMEZONE

    if not any([new_title, new_start_iso, new_end_iso]):
        raise ValueError("You must specify at least one field to update.")

    service = get_calendar_service()

    calendar_id = MANAGED_CALENDAR_ID
    if not calendar_id:
        raise ValueError("MANAGED_CALENDAR_ID is not configured.")

    target_event_id = event_id
    if target_event_id is None:
        if not event_title:
            raise ValueError("Provide either event_id or event_title to locate the event.")

        now_iso = datetime.utcnow().isoformat() + "Z"
        search = (
            service.events()
            .list(
                calendarId=calendar_id,
                q=event_title,
                timeMin=now_iso,
                maxResults=5,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = search.get("items", [])
        if not items:
            raise ValueError(f'No upcoming event found matching title "{event_title}".')
        target_event_id = items[0].get("id")
        if not target_event_id:
            raise ValueError("Found event has no ID; cannot update.")

    patch: dict = {}
    if new_title is not None:
        patch["summary"] = new_title
    if new_start_iso is not None:
        patch["start"] = {"dateTime": new_start_iso, "timeZone": timezone}
    if new_end_iso is not None:
        patch["end"] = {"dateTime": new_end_iso, "timeZone": timezone}

    updated = update_event(service, calendar_id, target_event_id, patch)
    return {
        "id": updated.get("id"),
        "summary": updated.get("summary"),
        "start": updated.get("start"),
        "end": updated.get("end"),
    }


@function_tool
def delete_event_tool(
    event_title: str | None = None,
    event_id: str | None = None,
) -> Dict[str, Any]:
    """
    Delete an event from the managed calendar.

    Args:
        event_title: Title query to locate the event (used if event_id not provided).
        event_id: The Google Calendar event ID to delete (preferred when known).

    Returns:
        A dict indicating success and the deleted event ID.
    """
    service = get_calendar_service()
    calendar_id = MANAGED_CALENDAR_ID
    if not calendar_id:
        raise ValueError("MANAGED_CALENDAR_ID is not configured.")

    target_event_id = event_id
    if target_event_id is None:
        if not event_title:
            raise ValueError("Provide either event_id or event_title to locate the event.")
        now_iso = datetime.utcnow().isoformat() + "Z"
        search = (
            service.events()
            .list(
                calendarId=calendar_id,
                q=event_title,
                timeMin=now_iso,
                maxResults=5,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = search.get("items", [])
        if not items:
            raise ValueError(f'No upcoming event found matching title "{event_title}".')
        target_event_id = items[0].get("id")
        if not target_event_id:
            raise ValueError("Found event has no ID; cannot delete.")

    ok = delete_event(service, calendar_id, target_event_id)
    return {"success": ok, "deleted_event_id": target_event_id}


@function_tool
def freebusy_tool(
    time_min_iso: str,
    time_max_iso: str,
    include_managed_calendar_only: bool = True,
) -> Dict[str, Any]:
    """
    Check busy time slots using the Freebusy API.

    Args:
        time_min_iso: Start of the window in ISO format (UTC or with offset).
        time_max_iso: End of the window in ISO format.
        include_managed_calendar_only: If True, only check the managed calendar.

    Returns:
        A dict mapping calendar IDs to their busy periods.
    """
    def _normalize_iso(ts: str) -> str:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
        return dt.astimezone(ZoneInfo(TIMEZONE)).isoformat()

    service = get_calendar_service()

    if include_managed_calendar_only:
        calendar_ids = [MANAGED_CALENDAR_ID]
    else:
        calendar_ids = [MANAGED_CALENDAR_ID]

    if not calendar_ids or not calendar_ids[0]:
        raise ValueError("MANAGED_CALENDAR_ID is not configured.")

    normalized_min = _normalize_iso(time_min_iso)
    normalized_max = _normalize_iso(time_max_iso)

    try:
        raw = freebusy_query(service, normalized_min, normalized_max, calendar_ids)
    except HttpError as err:
        return {
            "error": "Google Calendar API error",
            "status": getattr(err, "status_code", None),
            "details": str(err),
        }
    calendar_id = calendar_ids[0]
    busy_periods = raw.get(calendar_id, {}).get("busy", [])

    def _to_brussels_iso(iso_str: str) -> str:
        normalized = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.astimezone(ZoneInfo(TIMEZONE)).isoformat()

    busy_brussels = []
    for slot in busy_periods:
        start = slot.get("start")
        end = slot.get("end")
        if not start or not end:
            continue
        busy_brussels.append({"start": _to_brussels_iso(start), "end": _to_brussels_iso(end)})

    summary = "Busy during the requested window." if busy_brussels else "Free during the requested window."

    return {
        "calendar_id": calendar_id,
        "timezone": TIMEZONE,
        "time_window_local": {"start": normalized_min, "end": normalized_max},
        "busy": bool(busy_brussels),
        "busy_slots_local": busy_brussels,
        "summary": summary,
        "raw": raw,
    }
