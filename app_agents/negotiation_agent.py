from __future__ import annotations

import os
import json
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

from agents import Agent, AgentOutputSchema, Runner, function_tool, set_default_openai_client
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

from calendar_client import freebusy_query, get_calendar_service
from calendar_tools_agent import list_upcoming_events_tool, freebusy_tool
from models import AlternativeSlot, NegotiationOutcome, MutationPlan, ResolutionOption, ScheduleEvent

load_dotenv()

TIMEZONE = os.getenv("TIMEZONE", "Europe/Brussels")
REQUIRED_RESPONSES_API_VERSION = "2025-03-01-preview"


def _resolve_api_version() -> str:
    env_version = os.getenv("AZURE_OPENAI_API_VERSION") or os.getenv("OPENAI_VERSION_NAME")
    if env_version and env_version.startswith("2025"):
        return env_version
    return REQUIRED_RESPONSES_API_VERSION


def _require_env(name: str, fallback: str | None = None) -> str:
    val = os.getenv(name) or (os.getenv(fallback) if fallback else None)
    if not val:
        missing = f"{name}" if not fallback else f"{name} or {fallback}"
        raise RuntimeError(f"Missing environment variable: {missing}")
    return val


client = AsyncAzureOpenAI(
    api_key=_require_env("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"),
    api_version=_resolve_api_version(),
    azure_endpoint=_require_env("AZURE_OPENAI_ENDPOINT", "OPENAI_ENDPOINT"),
)
set_default_openai_client(client, use_for_tracing=False)

MODEL = (
    os.getenv("AZURE_OPENAI_DEPLOYMENT")
    or os.getenv("OPENAI_DEPLOYMENT_NAME")
    or os.getenv("OPENAI_MODEL_NAME")
    or "gpt-4o"
)


def _ensure_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(TIMEZONE))
    return dt


def _next_occurrence(event: ScheduleEvent) -> datetime:
    dow_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    target = dow_map.get(str(event.day_of_week), 0)
    today = datetime.now(ZoneInfo(TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (target - today.weekday()) % 7
    return today + timedelta(days=delta)


def _candidate_slots(event: ScheduleEvent, days_search_range: int = 7, step_minutes: int = 30) -> List[tuple[datetime, datetime]]:
    base_date = _next_occurrence(event)
    sh, sm = map(int, event.start_time.split(":"))
    eh, em = map(int, event.end_time.split(":"))
    base_start = base_date.replace(hour=sh, minute=sm)
    base_end = base_date.replace(hour=eh, minute=em)
    duration = base_end - base_start

    candidates: List[tuple[datetime, datetime]] = []
    for delta_days in range(-days_search_range, days_search_range + 1):
        day = base_start + timedelta(days=delta_days)
        day = day.replace(hour=base_start.hour, minute=base_start.minute, second=0, microsecond=0)
        for step in range(0, 12 * 60, step_minutes):  # 12h window
            start = day + timedelta(minutes=step)
            end = start + duration
            candidates.append((_ensure_dt(start), _ensure_dt(end)))
    return candidates


def _filter_free_slots(candidates: List[tuple[datetime, datetime]], calendar_id: str) -> List[AlternativeSlot]:
    if not candidates:
        return []
    service = get_calendar_service()
    time_min = min(s for s, _ in candidates).isoformat()
    time_max = max(e for _, e in candidates).isoformat()
    busy_resp = freebusy_query(service, time_min, time_max, [calendar_id])
    busy = busy_resp.get(calendar_id, {}).get("busy", [])

    def is_free(start: datetime, end: datetime) -> bool:
        for block in busy:
            b_start = _ensure_dt(datetime.fromisoformat(block.get("start")))
            b_end = _ensure_dt(datetime.fromisoformat(block.get("end")))
            if max(start, b_start) < min(end, b_end):
                return False
        return True

    free_slots: List[AlternativeSlot] = []
    for start, end in candidates:
        if is_free(start, end):
            delta = abs((start - candidates[0][0]).total_seconds())
            free_slots.append(
                AlternativeSlot(
                    start_iso=start.isoformat(),
                    end_iso=end.isoformat(),
                    score=-delta,  # closer to original start is better
                )
            )
    return sorted(free_slots, key=lambda s: s.score or 0, reverse=True)


@function_tool
def find_alternative_slots_tool(
    event_json: str,
    calendar_id: str,
    days_search_range: int = 7,
    step_minutes: int = 30,
) -> List[dict]:
    """
    Returns a list of free alternative slots for the given event (scored by proximity).
    Accepts event as JSON string to avoid strict schema issues.
    """
    evt = ScheduleEvent.model_validate_json(event_json)
    candidates = _candidate_slots(evt, days_search_range=days_search_range, step_minutes=step_minutes)
    slots = _filter_free_slots(candidates, calendar_id)
    return [slot.model_dump() for slot in slots]


@function_tool
def apply_resolutions_tool(
    mutation_plan_json: str,
    resolutions_json: str,
) -> dict:
    """
    Apply resolution suggestions (new start/end ISO) to a MutationPlan.
    Accepts/returns JSON-friendly dicts to keep schema loose.
    """
    new_plan = MutationPlan.model_validate_json(mutation_plan_json)
    raw_resolutions = json.loads(resolutions_json) if isinstance(resolutions_json, str) else resolutions_json
    resolutions: List[ResolutionOption] = [
        ResolutionOption.model_validate(r) if not isinstance(r, ResolutionOption) else r
        for r in raw_resolutions or []
    ]
    ops = getattr(new_plan, "operations", [])

    applied: List[ResolutionOption] = []
    for res in resolutions:
        idx = res.operation_index
        if idx < 0 or idx >= len(ops):
            continue
        op = ops[idx]
        if getattr(op, "op", None) != "create_recurring":
            continue
        ev: ScheduleEvent = getattr(op, "event", None)
        if not ev:
            continue
        try:
            start_dt = datetime.fromisoformat(res.suggested_start_iso)
            end_dt = datetime.fromisoformat(res.suggested_end_iso)
            ev.start_time = start_dt.strftime("%H:%M")
            ev.end_time = end_dt.strftime("%H:%M")
            applied.append(res)
        except Exception:
            continue

    outcome = NegotiationOutcome(
        updated_plan=new_plan,
        applied_resolutions=applied,
        unresolved_conflicts=[],
    )
    return outcome.model_dump()


negotiation_agent = Agent(
    name="NegotiationAgent",
    model=MODEL,
    instructions=(
        "You resolve scheduling conflicts in a MutationPlan. "
        "Given a MutationPlan and a ConflictReport, find better time slots using the provided tools, "
        "favor minimal changes, and produce a NegotiationOutcome with an updated plan. "
        "Always prefer nearby slots and keep day-of-week when possible. "
        "Use find_alternative_slots_tool to discover options, and apply_resolutions_tool to produce the revised plan."
    ),
    tools=[
        find_alternative_slots_tool,
        apply_resolutions_tool,
        freebusy_tool,
        list_upcoming_events_tool,
    ],
    output_type=AgentOutputSchema(NegotiationOutcome, strict_json_schema=False),
)


def run_negotiation_agent(
    mutation_plan: MutationPlan,
    conflict_report,
    calendar_id: str,
) -> NegotiationOutcome:
    """
    Run the negotiation agent to resolve conflicts and return a NegotiationOutcome.
    """
    # Prepare a compact input message
    input_text = (
        "Resolve conflicts in the provided plan. "
        "Keep events close to their original times. "
        "Use find_alternative_slots_tool to propose new times, then apply_resolutions_tool to finalize. "
        "Return only a NegotiationOutcome."
    )
    content = [
        {"role": "user", "content": [{"type": "input_text", "text": input_text}]},
        {"role": "user", "content": [{"type": "input_text", "text": f"MutationPlan: {mutation_plan.model_dump_json()}"}]},
        {"role": "user", "content": [{"type": "input_text", "text": f"ConflictReport: {conflict_report.model_dump_json()}"}]},
    ]

    result = Runner.run_sync(
        negotiation_agent,
        input=content,
    )
    return result.final_output  # type: ignore[return-value]
