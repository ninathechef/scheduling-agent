"""
Simple helper functions used by the calendar agent shim.
These wrap the calendar_client module directly.
"""

from __future__ import annotations

from typing import Any, Dict, List

from calendar_client import (
    create_event,
    get_calendar_service,
    list_upcoming_events,
)
import os
from datetime import datetime, timedelta


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


def create_simple_event_tool(user_query: str) -> str:
    """
    Creates a quick event 30 minutes from now with a default duration.
    This is a placeholder to demonstrate tool usage without parsing details
    from the user query.
    """
    service = get_calendar_service()
    calendar_id = os.getenv("MANAGED_CALENDAR_ID")
    if not calendar_id:
        return "Cannot create event: MANAGED_CALENDAR_ID is not set."

    now = datetime.utcnow()
    start_dt = now + timedelta(minutes=30)
    end_dt = start_dt + timedelta(minutes=30)

    created = create_event(
        service,
        calendar_id=calendar_id,
        summary="Quick event",
        start_dt=start_dt,
        end_dt=end_dt,
        timezone=os.getenv("TIMEZONE", "UTC"),
    )
    return f"Created event '{created.get('summary')}' starting at {created['start'].get('dateTime')}"
