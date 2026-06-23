"""Tests for Phase 2 AI loop — stream_events, tool-use, AgentRun."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

pytest.importorskip("httpx")

from chirp.ai.agent import AgentRun
from chirp.ai.llm import LLM
from chirp.ai.memory import InMemoryConversationStore
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import ToolDef, ToolRegistry


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., Any],
) -> None:
    import httpx

    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)


def _registry_with_echo() -> ToolRegistry:
    bus = ToolEventBus()

    async def echo(message: str) -> str:
        return f"echo:{message}"

    tools = [
        ToolDef(
            name="echo",
            description="Echo",
            handler=echo,
            schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )
    ]
    return ToolRegistry(tools, bus)


class TestStreamEvents:
    @pytest.mark.asyncio
    async def test_openai_stream_events(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            lines = [
                'data: {"choices":[{"delta":{"content":"Hi"}}]}',
                "data: [DONE]",
            ]
            return httpx.Response(200, content="\n".join(lines).encode())

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        events = [e async for e in llm.stream_events("Hello")]
        assert [type(e).__name__ for e in events] == ["TokenEvent", "DoneEvent"]
        assert events[0].text == "Hi"  # type: ignore[union-attr]


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_openai_tool_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            body = json.loads(request.content)
            if calls["n"] == 1:
                assert body.get("tools")
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "echo",
                                                "arguments": '{"message": "hi"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "done"}}]},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        registry = _registry_with_echo()
        completion = await llm.complete(
            [{"role": "user", "content": "echo hi"}],
            tools=registry,
        )
        assert completion.tool_calls[0]["name"] == "echo"


@pytest.mark.issue(431)
@pytest.mark.issue(432)
@pytest.mark.issue(433)
class TestAgentRun:
    @pytest.mark.asyncio
    async def test_agent_tool_then_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            body = json.loads(request.content)
            if calls["n"] == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "c1",
                                            "type": "function",
                                            "function": {
                                                "name": "echo",
                                                "arguments": '{"message": "x"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            if body.get("stream"):
                lines = [
                    'data: {"choices":[{"delta":{"content":"OK"}}]}',
                    "data: [DONE]",
                ]
                return httpx.Response(200, content="\n".join(lines).encode())
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": ""}}]},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        store = InMemoryConversationStore()
        agent = AgentRun(llm, _registry_with_echo(), store=store)
        events = [e async for e in agent.stream("go")]
        types = [type(e).__name__ for e in events]
        assert "StreamToolCallEvent" in types
        assert types[-2:] == ["TokenEvent", "DoneEvent"]
