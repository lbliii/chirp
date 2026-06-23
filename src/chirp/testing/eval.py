"""LLM and agent eval helpers for TestClient-based regression tests.

These utilities mock provider HTTP at the httpx transport layer so AI routes
and :class:`~chirp.ai.agent.AgentRun` loops can be tested without live API keys.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from chirp.testing.sse import SSETestResult


@dataclass(slots=True)
class LLMScript:
    """Scripted OpenAI-compatible chat completion responses for mocked LLM calls."""

    completes: list[dict[str, Any]]
    stream_tokens: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LLMCallTracker:
    """Counts how many complete vs stream requests the mock served."""

    complete_calls: int = 0
    stream_calls: int = 0
    captured_messages: list[list[dict[str, Any]]] = field(default_factory=list)


def openai_completion(
    content: str = "",
    *,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a mock ``/v1/chat/completions`` response body."""
    message: dict[str, Any] = {"role": "assistant", "content": content or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def openai_tool_call(name: str, /, **arguments: Any) -> dict[str, Any]:
    """Build a single OpenAI ``tool_calls`` entry."""
    return {
        "id": f"call_{name}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def install_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., Any],
) -> None:
    """Patch ``httpx.AsyncClient`` so chirp.ai provider calls use *handler*."""
    import httpx

    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)


def install_llm_script(
    monkeypatch: pytest.MonkeyPatch,
    script: LLMScript,
    *,
    tags_response: dict[str, Any] | None = None,
) -> LLMCallTracker:
    """Install a scripted LLM mock for AgentRun / LLM HTTP calls."""
    import httpx

    tracker = LLMCallTracker()
    tags = tags_response or {"models": []}
    completes = script.completes or [openai_completion("")]
    tokens = script.stream_tokens

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(200, json=tags)

        body = json.loads(request.content)
        if body.get("stream"):
            tracker.stream_calls += 1
            lines = [
                f"data: {json.dumps({'choices': [{'delta': {'content': token}}]})}"
                for token in tokens
            ]
            lines.append("data: [DONE]")
            return httpx.Response(200, content="\n".join(lines).encode())

        tracker.complete_calls += 1
        if "messages" in body:
            tracker.captured_messages.append(body["messages"])
        idx = min(tracker.complete_calls - 1, len(completes) - 1)
        return httpx.Response(200, json=completes[idx])

    install_mock_transport(monkeypatch, handler)
    return tracker


def collect_sse_message_text(result: SSETestResult) -> str:
    """Join default ``message`` SSE event payloads into one string."""
    return "".join(
        event.data
        for event in result.events
        if (event.event or "message") == "message" and event.data
    )


def assert_tool_messages_contain(
    messages: list[dict[str, Any]],
    *,
    tool_name: str | None = None,
    text: str | None = None,
) -> None:
    """Assert a later completion round includes tool result messages."""
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "Expected at least one tool result message"
    if text is not None:
        joined = " ".join(str(m.get("content", "")) for m in tool_msgs)
        assert text in joined, f"Expected {text!r} in tool messages, got {joined!r}"
    if tool_name is not None:
        # OpenAI tool results don't repeat the name; inspect captured assistant tool_calls
        assistant = [m for m in messages if m.get("role") == "assistant"]
        names = {
            call.get("function", {}).get("name")
            for msg in assistant
            for call in (msg.get("tool_calls") or [])
        }
        assert tool_name in names, f"Expected tool {tool_name!r} in assistant tool_calls"
