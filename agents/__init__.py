"""
Lightweight stand-in for an agent runner.

This keeps the calendar demo working without the real Azure Agents SDK by
providing minimal Agent/Runner primitives. Runner.run simply calls a
callable tool if the agent provides one; otherwise it returns a fallback
message.
"""

from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

_default_client: Any = None


def set_default_openai_client(client: Any) -> None:
    """Store a default client for downstream use (not used in this shim)."""
    global _default_client
    _default_client = client


@dataclass
class Agent:
    name: str
    instructions: str
    tools: List[Callable[..., Any]] = field(default_factory=list)
    model: Optional[str] = None


class Runner:
    """Tiny async runner that executes the first tool, if any, passing input text."""

    @staticmethod
    async def run(agent: Agent, input: str):
        # If tools are provided, try the first one. This is a simplification
        # compared to a real LLM tool-calling workflow.
        if agent.tools:
            tool = agent.tools[0]
            try:
                output = tool(input)
            except Exception as exc:  # pragma: no cover - defensive UI fallback
                output = f"Tool error: {exc}"
        else:
            output = "No tools configured for this agent."

        return types.SimpleNamespace(final_output=output)
