"""Unified stream events for LLM and agent loops.

All streaming paths (``LLM.stream_events``, ``AgentRun.stream``) yield this
union. Distinct from ``chirp.tools.events.ToolCallEvent``, which fires after
a tool handler completes for activity dashboards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chirp.ai.errors import AIError


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """Incremental text token from the model."""

    text: str


@dataclass(frozen=True, slots=True)
class StreamToolCallEvent:
    """Model requested a tool invocation (pending dispatch)."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StreamToolResultEvent:
    """Tool dispatch completed (success or handler error string)."""

    call_id: str
    result: Any
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """Provider or framework error surfaced on the stream."""

    error: AIError


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """Stream finished normally."""

    tokens_out: int | None = None


type StreamEvent = TokenEvent | StreamToolCallEvent | StreamToolResultEvent | ErrorEvent | DoneEvent
