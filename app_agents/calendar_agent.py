from __future__ import annotations

import asyncio
import os
from typing import Optional

from agents import Agent, Runner, set_default_openai_client
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

from calendar_tools_agent import (
    create_simple_event_tool,
    delete_event_tool,
    freebusy_tool,
    list_upcoming_events_tool,
    update_event_tool,
)

# Ensure .env is loaded before we read env vars
load_dotenv()


def _require_env(name: str, fallback: Optional[str] = None) -> str:
    """
    Return the environment variable or fallback; raise if neither is set.
    """
    val = os.getenv(name) or (os.getenv(fallback) if fallback else None)
    if val:
        return val
    missing = f"{name}" if not fallback else f"{name} or {fallback}"
    raise RuntimeError(f"Missing environment variable: {missing}")


REQUIRED_RESPONSES_API_VERSION = "2025-03-01-preview"


def _resolve_api_version() -> str:
    """
    Ensure we always use an API version that supports the Responses API.
    """
    env_version = os.getenv("AZURE_OPENAI_API_VERSION") or os.getenv("OPENAI_VERSION_NAME")

    if env_version and env_version.startswith("2025"):
        return env_version

    # Force minimum supported version for the agents library.
    return REQUIRED_RESPONSES_API_VERSION


azure_client = AsyncAzureOpenAI(
    api_key=_require_env("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"),
    api_version=_resolve_api_version(),
    azure_endpoint=_require_env("AZURE_OPENAI_ENDPOINT", "OPENAI_ENDPOINT"),
)

# Register the Azure client for the agents SDK and disable tracing to avoid key conflicts.
set_default_openai_client(azure_client, use_for_tracing=False)
if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]

MODEL = (
    os.getenv("AZURE_OPENAI_DEPLOYMENT")
    or os.getenv("OPENAI_DEPLOYMENT_NAME")
    or os.getenv("OPENAI_MODEL_NAME")
    or "gpt-4o"
)

calendar_agent = Agent(
    name="Calendar Agent",
    model=MODEL,
    instructions=(
        "You manage a student's calendar. "
        "Use the provided tools to read and write Google Calendar events. "
        "Ask concise follow-up questions when required details (title, start/end, timezone) are missing. "
        "Keep responses short, confirm actions clearly, and avoid guessing times."
    ),
    tools=[
        list_upcoming_events_tool,
        create_simple_event_tool,
        update_event_tool,
        delete_event_tool,
        freebusy_tool,
    ],
)


async def _ask_calendar_agent(user_message: str) -> str:
    """
    Run the calendar agent asynchronously and return its final response.
    """
    result = await Runner().run(
        starting_agent=calendar_agent,
        input=user_message,
        max_turns=4,
    )
    return result.final_output


def run_calendar_agent(user_message: str) -> str:
    """
    Synchronous helper for Streamlit entrypoints.
    """
    return asyncio.run(_ask_calendar_agent(user_message))
