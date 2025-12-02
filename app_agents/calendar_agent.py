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
    create_recurring_event_tool,
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
    os.environ["AZURE_OPENAI_API_VERSION"] = REQUIRED_RESPONSES_API_VERSION
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
        create_recurring_event_tool,
    ],
)


def _format_with_history(history: list[dict[str, str]], user_message: str) -> str:
    """
    Combine prior turns with the new user message for lightweight memory.
    Each history item is expected to have 'role' ('user' or 'assistant') and 'content'.
    """
    if not history:
        return user_message
    lines = ["Previous conversation:"]
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        lines.append(f"{role.capitalize()}: {content}")
    lines.append(f"User: {user_message}")
    lines.append("Respond to the latest user request.")
    return "\n".join(lines)


async def _ask_calendar_agent(user_message: str, history: list[dict[str, str]] | None = None) -> str:
    """
    Run the calendar agent asynchronously and return its final response.
    """
    formatted_input = _format_with_history(history or [], user_message)
    result = await Runner().run(
        starting_agent=calendar_agent,
        input=formatted_input,
        max_turns=4,
    )
    return result.final_output


def run_calendar_agent(user_message: str, history: list[dict[str, str]] | None = None) -> str:
    """
    Synchronous helper for Streamlit entrypoints.
    """
    return asyncio.run(_ask_calendar_agent(user_message, history))
