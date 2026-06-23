"""Tests for AgentRun human-in-the-loop approval pauses."""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("httpx")

from chirp.ai.agent import AgentRun
from chirp.ai.events import StreamToolApprovalEvent, StreamToolResultEvent
from chirp.ai.llm import LLM
from chirp.ai.memory import InMemoryConversationStore
from chirp.tools.approval import InMemoryToolApprovalStore
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import ToolDef, ToolRegistry


def _install_mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    import httpx

    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)


def _registry_with_dangerous_tool() -> ToolRegistry:
    bus = ToolEventBus()

    async def delete_all() -> str:
        return "deleted"

    tools = [
        ToolDef(
            name="delete_all",
            description="Delete all records",
            handler=delete_all,
            schema={"type": "object", "properties": {}},
            approval_required=True,
        )
    ]
    return ToolRegistry(tools, bus)


@pytest.mark.issue(442)
class TestAgentRunApproval:
    @pytest.mark.asyncio
    async def test_pauses_with_approval_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
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
                                            "name": "delete_all",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        store = InMemoryConversationStore()
        approvals = InMemoryToolApprovalStore()
        agent = AgentRun(
            llm, _registry_with_dangerous_tool(), store=store, approval_store=approvals
        )
        events = [e async for e in agent.stream("delete everything")]
        assert len(events) == 1
        assert isinstance(events[0], StreamToolApprovalEvent)
        assert events[0].name == "delete_all"

    @pytest.mark.asyncio
    async def test_resume_after_approval_executes_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
                                                "name": "delete_all",
                                                "arguments": "{}",
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
                    'data: {"choices":[{"delta":{"content":"Done"}}]}',
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
        approvals = InMemoryToolApprovalStore()
        agent = AgentRun(
            llm, _registry_with_dangerous_tool(), store=store, approval_store=approvals
        )

        pause_events = [e async for e in agent.stream("delete everything")]
        approval_event = pause_events[0]
        assert isinstance(approval_event, StreamToolApprovalEvent)
        await approvals.mark_approved(approval_event.approval_id)

        resume_events = [
            e
            async for e in agent.stream(
                "",
                append_user=False,
                resume_approval_id=approval_event.approval_id,
            )
        ]
        types = [type(e).__name__ for e in resume_events]
        assert "StreamToolResultEvent" in types
        assert types[-2:] == ["TokenEvent", "DoneEvent"]
        result_event = next(e for e in resume_events if isinstance(e, StreamToolResultEvent))
        assert result_event.error is None
        assert result_event.result == "deleted"

    @pytest.mark.asyncio
    async def test_resume_after_deny_skips_execution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
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
                                                "name": "delete_all",
                                                "arguments": "{}",
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            if json.loads(request.content).get("stream"):
                lines = [
                    'data: {"choices":[{"delta":{"content":"Skipped"}}]}',
                    "data: [DONE]",
                ]
                return httpx.Response(200, content="\n".join(lines).encode())
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": ""}}]},
            )

        _install_mock_transport(monkeypatch, handler)
        llm = LLM("openai:gpt-4o", api_key="sk-test")
        approvals = InMemoryToolApprovalStore()
        agent = AgentRun(
            llm,
            _registry_with_dangerous_tool(),
            store=InMemoryConversationStore(),
            approval_store=approvals,
        )
        pause: StreamToolApprovalEvent | None = None
        async for event in agent.stream("delete everything"):
            pause = event
            break
        assert isinstance(pause, StreamToolApprovalEvent)
        await approvals.mark_denied(pause.approval_id)

        resume_events = [
            e
            async for e in agent.stream("", append_user=False, resume_approval_id=pause.approval_id)
        ]
        result = next(e for e in resume_events if isinstance(e, StreamToolResultEvent))
        assert result.result is None
        assert result.error is not None
