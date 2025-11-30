from __future__ import annotations

import json
import os
from typing import List

from agents import Agent, AgentOutputSchema, Runner, set_default_openai_client
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

from models import MutationPlan, ScheduleEvent, SemesterWindow

load_dotenv()

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

planner_agent = Agent(
    name="PlannerAgent",
    model=MODEL,
    instructions=(
        "You are a planning agent that turns extracted class schedule events into a concrete calendar mutation plan.\n\n"
        "You will receive:\n"
        "- A list of ScheduleEvent objects (title, day_of_week, start_time, end_time, location, recurrence).\n"
        "- A SemesterWindow with semester_start, semester_end, timezone.\n\n"
        "Your job is to produce a MutationPlan.\n"
        "Rules:\n"
        "- For now, only use create_recurring operations (no update or delete).\n"
        "- Assume each ScheduleEvent is a weekly class across the entire semester unless recurrence is 'once'.\n"
        "- For weekly classes, create one CreateRecurringOp per ScheduleEvent:\n"
        "    * first_start_iso and first_end_iso must be the first occurrence of this class that falls on the correct weekday within the semester window.\n"
        "    * rrule must be a valid RRULE string with FREQ=WEEKLY, BYDAY=..., and UNTIL equal to the last day of the semester at 23:59:59Z.\n"
        "- preview should be a human-readable summary listing each class, weekday, and time.\n"
        "- requires_confirmation must be True.\n"
        "- Make sure end time is after start time. If something is invalid, you may drop that entry."
    ),
    output_type=AgentOutputSchema(MutationPlan, strict_json_schema=False),
)


def run_planner_agent(
    events: List[ScheduleEvent],
    semester: SemesterWindow,
) -> MutationPlan:
    """
    Use the PlannerAgent to generate a MutationPlan from schedule events and a semester window.
    """
    payload = {
        "events": [e.model_dump() if hasattr(e, "model_dump") else e for e in events],
        "semester": semester.model_dump() if hasattr(semester, "model_dump") else semester,
    }

    user_content = [
        {
            "type": "input_text",
            "text": (
                "Here is the extracted schedule and semester window as JSON. "
                "Use it to construct a valid MutationPlan."
            ),
        },
        {
            "type": "input_text",
            "text": json.dumps(payload),
        },
    ]

    result = Runner.run_sync(
        planner_agent,
        input=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
    )

    plan: MutationPlan = result.final_output  # type: ignore[assignment]
    return plan
