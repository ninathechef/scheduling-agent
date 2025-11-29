# agents/calendar_agent.py
from __future__ import annotations

import asyncio

from agents import Agent, Runner, set_default_openai_client
from ai_client import get_azure_openai_client, get_deployment_name
from calendar_tools_agent import (
    list_upcoming_events_tool,
    create_simple_event_tool,
)

# 1) Configure Azure client as the default for all agents
openai_client = get_azure_openai_client()
set_default_openai_client(openai_client)

MODEL = get_deployment_name()  # Azure deployment name


# 2) Define the Calendar Agent
calendar_agent = Agent(
    name="CalendarAgent",
    instructions=(
        "You help manage a student's calendar. "
        "You ALWAYS use the available tools to read or write events, "
        "instead of making things up. "
        "If the user does not provide enough info (like date/time), "
        "ask clear follow-up questions to disambiguate."
    ),
    tools=[list_upcoming_events_tool, create_simple_event_tool],
    model=MODEL,
)


# 3) Runner helper (async + sync wrapper)

async def _run_calendar_agent_async(user_message: str) -> str:
    """
    Runs the calendar agent with the given user message and returns final text output.
    """
    result = await Runner.run(calendar_agent, input=user_message)
    # result.final_output is generally a string (model's final response)
    return str(result.final_output)


def run_calendar_agent(user_message: str) -> str:
    """
    Synchronous wrapper so non-async code (like Streamlit callbacks) can call the agent.
    """
    return asyncio.run(_run_calendar_agent_async(user_message))
