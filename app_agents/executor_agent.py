from __future__ import annotations

import json
import os
from typing import List

from agents import Agent, Runner, set_default_openai_client
from dotenv import load_dotenv
from openai import AsyncOpenAI, AsyncAzureOpenAI

from calendar_tools_agent import (
    create_recurring_event_tool,
    update_event_tool,
    delete_event_tool,
)
from models import MutationPlan, ExecutionReport, ExecutionResult

load_dotenv()


def _build_client():
    """
    Prefer Azure configuration when available, otherwise fall back to OpenAI.
    """
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    azure_version = os.getenv("AZURE_OPENAI_API_VERSION") or os.getenv("OPENAI_VERSION_NAME")

    if azure_endpoint and azure_key and azure_version:
        if not azure_version.startswith("2025"):
            azure_version = "2025-03-01-preview"
            os.environ["AZURE_OPENAI_API_VERSION"] = azure_version
        return AsyncAzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version=azure_version,
        )

    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


client = _build_client()
set_default_openai_client(client)

MODEL = (
    os.getenv("AZURE_OPENAI_DEPLOYMENT")
    or os.getenv("OPENAI_DEPLOYMENT_NAME")
    or os.getenv("OPENAI_MODEL_NAME")
    or "gpt-4.1-mini"
)


executor_agent = Agent(
    name="CalendarExecutorAgent",
    model=MODEL,
    instructions=(
        "You are the executor of a MutationPlan. "
        "You receive a MutationPlan and must apply each operation in order, "
        "using the available calendar tools.\n\n"
        "Rules:\n"
        "- The input will be a single MutationPlan JSON object.\n"
        "- For now, operations can be:\n"
        "    * create_recurring: use create_recurring_event_tool\n"
        "    * update: use update_event_tool\n"
        "    * delete: use delete_event_tool\n"
        "- For each operation, you must record an ExecutionResult with:\n"
        "    * op_index: index in the list\n"
        "    * op_type: operation type\n"
        "    * status: 'success' or 'failed'\n"
        "    * message: short explanation\n"
        "    * google_event_id: if available\n"
        "- If a tool call fails or you detect invalid input, mark that op as failed "
        "and continue with the others.\n"
        "- Do NOT invent fake results.\n"
    ),
    tools=[create_recurring_event_tool, update_event_tool, delete_event_tool],
    output_type=ExecutionReport,
)


def run_executor_agent(plan: MutationPlan) -> ExecutionReport:
    """
    Use the ExecutorAgent to apply a MutationPlan to the calendar.
    """
    payload = plan.model_dump()

    user_content = [
        {
            "type": "input_text",
            "text": (
                "Here is a MutationPlan as JSON. "
                "Apply all operations using the tools and return an ExecutionReport."
            ),
        },
        {
            "type": "input_text",
            "text": json.dumps(payload),
        },
    ]

    result = Runner.run_sync(
        executor_agent,
        input=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
    )

    report: ExecutionReport = result.final_output  # type: ignore[assignment]
    return report
