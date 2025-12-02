from __future__ import annotations

import base64
import os
from typing import List

from agents import Agent, Runner, set_default_openai_client
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

from models import ScheduleEvent

# Load environment variables so we can configure the Azure client
load_dotenv()

REQUIRED_RESPONSES_API_VERSION = "2025-03-01-preview"


def _resolve_api_version() -> str:
    env_version = os.getenv("AZURE_OPENAI_API_VERSION") or os.getenv("OPENAI_VERSION_NAME")
    if env_version and env_version.startswith("2025"):
        return env_version
    # Force a compatible version when the env is too old.
    os.environ["AZURE_OPENAI_API_VERSION"] = REQUIRED_RESPONSES_API_VERSION
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

# Agent that extracts structured class schedule events from PDFs/images
document_agent = Agent(
    name="DocumentUnderstandingAgent",
    model=MODEL,
    instructions=(
        "You are an assistant that reads class schedules from documents (PDFs or images) "
        "and extracts structured class events as ScheduleEvent objects.\n"
        "The user will send a single document representing their class schedule.\n"
        "Guidelines:\n"
        "- Only include actual classes or recurring events (lectures, seminars, labs).\n"
        "- Ignore holidays, notes, or general text that is not a class.\n"
        "- Use 'weekly' recurrence for typical weekly classes.\n"
        "- Times should be in HH:MM 24-hour format.\n"
        "- Day of week must be one of: mon, tue, wed, thu, fri, sat, sun.\n"
        "- If information is missing (location, notes), you may leave it empty.\n"
        "- If the timetable suggests multiple weeks with the same pattern, treat classes as weekly recurring events."
    ),
    output_type=List[ScheduleEvent],
)


def run_document_agent(file_bytes: bytes, mime_type: str) -> List[ScheduleEvent]:
    """
    Runs the DocumentUnderstandingAgent on the given file bytes and MIME type,
    returning a list of ScheduleEvent instances.
    """
    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    if mime_type == "application/pdf":
        content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "This is a PDF of a class schedule. "
                            "Extract all recurring class events as ScheduleEvent objects."
                        ),
                    },
                    {"type": "input_image", "image_url": f"data:application/pdf;base64,{b64_data}"},
                ],
            }
        ]
    else:
        content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "This is an image of a class schedule. "
                            "Extract all recurring class events as ScheduleEvent objects."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{b64_data}",
                    },
                ],
            }
        ]

    result = Runner.run_sync(
        document_agent,
        input=content,
    )

    events: List[ScheduleEvent] = result.final_output  # type: ignore[assignment]
    return events
