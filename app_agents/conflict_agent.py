from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

from calendar_client import get_calendar_service
from models import Conflict, ConflictReport, MutationPlan, ScheduleEvent, SemesterWindow

TIMEZONE = os.getenv("TIMEZONE", "Europe/Brussels")


def _parse_time_hhmm(value: str) -> tuple[int, int]:
    hour, minute = map(int, value.split(":"))
    return hour, minute


def _first_occurrence_date(semester_start: datetime, target_dow: str) -> datetime:
    # semester_start is date; target_dow is mon..sun
    dow_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    target = dow_map.get(target_dow.lower(), 0)
    start_dow = semester_start.weekday()
    delta_days = (target - start_dow) % 7
    return semester_start + timedelta(days=delta_days)


def _events_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def _planned_occurrences(plan: MutationPlan, semester: SemesterWindow) -> List[dict]:
    tz = ZoneInfo(semester.timezone)
    semester_start_date = datetime.fromisoformat(semester.semester_start).replace(tzinfo=tz)

    planned = []
    for idx, op in enumerate(plan.operations):
        if getattr(op, "op", None) != "create_recurring":
            continue
        event: ScheduleEvent = getattr(op, "event", None)
        if not event:
            continue
        start_day = _first_occurrence_date(semester_start_date, event.day_of_week.value if hasattr(event, "day_of_week") else event.day_of_week)
        sh, sm = _parse_time_hhmm(event.start_time)
        eh, em = _parse_time_hhmm(event.end_time)
        start_dt = start_day.replace(hour=sh, minute=sm)
        end_dt = start_day.replace(hour=eh, minute=em)
        planned.append(
            {
                "index": idx,
                "title": event.title,
                "start": start_dt,
                "end": end_dt,
                "event": event,
            }
        )
    return planned


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(TIMEZONE))
    return dt


def _existing_events_between(service, calendar_id: str, start_iso: str, end_iso: str) -> List[dict]:
    """
    Fetch existing events in the given window and normalize start/end to datetime.
    """
    resp = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        )
        .execute()
    )
    events = []
    for ev in resp.get("items", []):
        start_raw = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
        end_raw = ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date")
        if not start_raw or not end_raw:
            continue
        try:
            start_dt = _ensure_tz(datetime.fromisoformat(start_raw))
            end_dt = _ensure_tz(datetime.fromisoformat(end_raw))
        except Exception:
            continue
        events.append(
            {
                "summary": ev.get("summary", "(busy)"),
                "start": start_dt,
                "end": end_dt,
            }
        )
    return events


def run_conflict_agent(plan: MutationPlan, semester: SemesterWindow, calendar_id: str) -> ConflictReport:
    """
    Deterministic conflict detection:
    - Checks overlaps within the planned events.
    - Checks conflicts with existing calendar busy blocks via freebusy.
    """
    service = get_calendar_service()
    tz = ZoneInfo(semester.timezone)

    conflicts: List[Conflict] = []

    planned = _planned_occurrences(plan, semester)

    # 1) Planned vs planned overlaps
    for i in range(len(planned)):
        for j in range(i + 1, len(planned)):
            a = planned[i]
            b = planned[j]
            if _events_overlap(a["start"], a["end"], b["start"], b["end"]):
                conflicts.append(
                    Conflict(
                        type="overlap",
                        summary=f"Planned '{a['title']}' overlaps with '{b['title']}'",
                        affected=[a["title"], b["title"]],
                        suggestions=["Shift one of the events to avoid overlap."],
                    )
                )

    # 2) Planned vs existing events/busy blocks
    for p in planned:
        start_iso = p["start"].astimezone(tz).isoformat()
        end_iso = p["end"].astimezone(tz).isoformat()
        existing = _existing_events_between(service, calendar_id, start_iso, end_iso)
        for ev in existing:
            if _events_overlap(p["start"], p["end"], ev["start"], ev["end"]):
                conflicts.append(
                    Conflict(
                        type="overlap",
                        summary=f"Planned '{p['title']}' overlaps with '{ev['summary']}'",
                        affected=[p["title"], ev["summary"]],
                        suggestions=["Adjust the time or reschedule around existing commitments."],
                    )
                )

    return ConflictReport(conflicts=conflicts, blocking=bool(conflicts))
