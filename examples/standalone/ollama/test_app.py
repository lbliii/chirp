"""Tests for the Ollama chat example.

Mocks Ollama HTTP at the transport layer — no real Ollama needed to run tests.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

pytest.importorskip("httpx")

from chirp.testing import TestClient


def _mcp(method: str, *, params: dict | None = None, rpc_id: int = 1) -> dict:
    """Build a JSON-RPC request body for MCP."""
    return {"jsonrpc": "2.0", "method": method, "id": rpc_id, "params": params or {}}


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


def _openai_complete(
    content: str = "",
    tool_calls: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a mock OpenAI-compatible /v1/chat/completions response."""
    msg: dict[str, Any] = {"role": "assistant", "content": content or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg}]}


def _tool_call(name: str, **arguments: Any) -> dict[str, Any]:
    """Build a single OpenAI tool_call object."""
    return {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def _install_llm_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    completes: list[dict[str, Any]],
    stream_tokens: list[str] | None = None,
) -> dict[str, int]:
    """Mock AgentRun LLM calls (complete rounds + final stream)."""
    import httpx

    state = {"n": 0}
    tokens = stream_tokens or []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

        body = json.loads(request.content)
        if body.get("stream"):
            lines = [
                f'data: {json.dumps({"choices": [{"delta": {"content": token}}]})}'
                for token in tokens
            ]
            lines.append("data: [DONE]")
            return httpx.Response(200, content="\n".join(lines).encode())

        idx = min(state["n"], len(completes) - 1)
        state["n"] += 1
        return httpx.Response(200, json=completes[idx])

    _install_mock_transport(monkeypatch, handler)
    return state


async def _seed_user(example_module: Any, text: str) -> None:
    await example_module._store.append("default", {"role": "user", "content": text})


# -------------------------------------------------------------------------
# Route tests
# -------------------------------------------------------------------------


class TestRoutes:
    """Verify the HTTP routes render correctly."""

    async def test_index_renders_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Ollama Chat" in response.text
            assert "Say something" in response.text

    async def test_index_shows_model_badge(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "llama3.2" in response.text

    async def test_index_has_stream_toggle(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'name="stream"' in response.text
            assert "checked" in response.text
            assert 'hx-post="/chat"' in response.text

    async def test_index_model_selector_avoids_js_hx_vals(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "hx-vals=" not in response.text

    async def test_clear_resets_conversation(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/clear")
            assert response.status == 200
            assert "cleared" in response.text.lower()

    async def test_switch_model(self, example_app, example_module) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/model",
                body=b"model=qwen3%3A8b",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert example_module._get_model() == "qwen3:8b"

    async def test_index_falls_back_without_ollama(self, example_app, monkeypatch) -> None:
        """When Ollama is unreachable, the index still renders with a static badge."""
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        _install_mock_transport(monkeypatch, handler)

        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "model-badge" in response.text


# -------------------------------------------------------------------------
# MCP tool tests
# -------------------------------------------------------------------------


class TestMCPTools:
    """Verify all 5 tools work via MCP JSON-RPC (no Ollama needed)."""

    async def test_tools_list_returns_all_five(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/mcp", json=_mcp("tools/list"))
            body = json.loads(response.text)
            tools = body["result"]["tools"]
            names = {t["name"] for t in tools}
            assert names == {
                "add_note",
                "list_notes",
                "search_notes",
                "get_current_time",
                "calculate",
            }

    async def test_add_note_via_mcp(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={
                        "name": "add_note",
                        "arguments": {"text": "Buy milk", "tag": "errands"},
                    },
                ),
            )
            body = json.loads(response.text)
            content = json.loads(body["result"]["content"][0]["text"])
            assert content["text"] == "Buy milk"
            assert content["tag"] == "errands"

    async def test_list_notes_via_mcp(self, example_app) -> None:
        async with TestClient(example_app) as client:
            await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "add_note", "arguments": {"text": "Test note"}},
                ),
            )
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "list_notes", "arguments": {}},
                ),
            )
            body = json.loads(response.text)
            notes = json.loads(body["result"]["content"][0]["text"])
            assert any(n["text"] == "Test note" for n in notes)

    async def test_search_notes_via_mcp(self, example_app) -> None:
        async with TestClient(example_app) as client:
            await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "add_note", "arguments": {"text": "Python docs"}},
                ),
            )
            await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "add_note", "arguments": {"text": "Rust guide"}},
                ),
            )
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "search_notes", "arguments": {"query": "python"}},
                ),
            )
            body = json.loads(response.text)
            results = json.loads(body["result"]["content"][0]["text"])
            assert len(results) == 1
            assert results[0]["text"] == "Python docs"

    async def test_get_current_time_via_mcp(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "get_current_time", "arguments": {}},
                ),
            )
            body = json.loads(response.text)
            text = body["result"]["content"][0]["text"]
            assert "UTC" in text

    async def test_calculate_via_mcp(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "calculate", "arguments": {"expression": "2 + 3 * 4"}},
                ),
            )
            body = json.loads(response.text)
            text = body["result"]["content"][0]["text"]
            assert text == "14"

    async def test_calculate_rejects_unsafe_input(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={
                        "name": "calculate",
                        "arguments": {"expression": "__import__('os')"},
                    },
                ),
            )
            body = json.loads(response.text)
            text = body["result"]["content"][0]["text"]
            assert "Error" in text


# -------------------------------------------------------------------------
# Non-streaming chat tests
# -------------------------------------------------------------------------


class TestChatNonStreaming:
    """Test the non-streaming chat path (stream toggle OFF).

    The non-streaming path is a two-step flow:
    1. POST /chat → user bubble + spinner (immediate feedback)
    2. GET /chat/complete → assistant response (deferred)
    """

    async def test_chat_post_returns_pending(self, example_app) -> None:
        """POST /chat without stream returns user bubble + spinner."""
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/chat",
                method="POST",
                body=b"message=Hello",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "msg-user" in response.text
            assert "Hello" in response.text
            assert "/chat/complete" in response.text

    async def test_chat_complete_returns_response(
        self, example_app, example_module, monkeypatch
    ) -> None:
        state = _install_llm_mock(
            monkeypatch,
            completes=[_openai_complete(content="")],
            stream_tokens=["Hello! How can I help?"],
        )
        await _seed_user(example_module, "Hello")

        async with TestClient(example_app) as client:
            response = await client.fragment("/chat/complete")
            assert response.status == 200
            assert "Hello! How can I help?" in response.text
            assert state["n"] == 1

    async def test_chat_empty_message_ignored(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/chat",
                method="POST",
                body=b"message=",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200

    async def test_chat_with_tool_call(self, example_app, example_module, monkeypatch) -> None:
        state = _install_llm_mock(
            monkeypatch,
            completes=[
                _openai_complete(tool_calls=[_tool_call("get_current_time")]),
                _openai_complete(content=""),
            ],
            stream_tokens=["It is currently 12:00 UTC."],
        )
        await _seed_user(example_module, "What time is it")

        async with TestClient(example_app) as client:
            response = await client.fragment("/chat/complete")
            assert response.status == 200
            assert "12:00 UTC" in response.text
            assert state["n"] == 2

    async def test_chat_with_calculate_tool(
        self, example_app, example_module, monkeypatch
    ) -> None:
        state = _install_llm_mock(
            monkeypatch,
            completes=[
                _openai_complete(tool_calls=[_tool_call("calculate", expression="2 + 2")]),
                _openai_complete(content=""),
            ],
            stream_tokens=["2 + 2 = 4"],
        )
        await _seed_user(example_module, "What is 2 plus 2")

        async with TestClient(example_app) as client:
            response = await client.fragment("/chat/complete")
            assert response.status == 200
            assert "2 + 2 = 4" in response.text
            assert state["n"] == 2

    async def test_chat_tool_results_sent_back(
        self, example_app, example_module, monkeypatch
    ) -> None:
        import httpx

        captured_messages: list[list[dict[str, Any]]] = []
        completes = [
            _openai_complete(tool_calls=[_tool_call("add_note", text="Remember this")]),
            _openai_complete(content=""),
        ]
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": []})
            body = json.loads(request.content)
            if body.get("stream"):
                lines = ['data: {"choices":[{"delta":{"content":"Done!"}}]}', "data: [DONE]"]
                return httpx.Response(200, content="\n".join(lines).encode())
            captured_messages.append(body["messages"])
            idx = min(state["n"], len(completes) - 1)
            state["n"] += 1
            return httpx.Response(200, json=completes[idx])

        _install_mock_transport(monkeypatch, handler)
        await _seed_user(example_module, "Remember this")

        async with TestClient(example_app) as client:
            await client.fragment("/chat/complete")

        assert len(captured_messages) == 2
        second_call_msgs = captured_messages[1]
        tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "Remember this" in tool_msgs[0]["content"]

    async def test_chat_shows_tools_used(self, example_app, example_module, monkeypatch) -> None:
        _install_llm_mock(
            monkeypatch,
            completes=[
                _openai_complete(tool_calls=[_tool_call("get_current_time")]),
                _openai_complete(content=""),
            ],
            stream_tokens=["It is noon."],
        )
        await _seed_user(example_module, "What time")

        async with TestClient(example_app) as client:
            response = await client.fragment("/chat/complete")
            assert "get_current_time" in response.text


# -------------------------------------------------------------------------
# Streaming chat tests
# -------------------------------------------------------------------------


class TestChatStreaming:
    """Test the streaming chat path (stream toggle ON)."""

    async def test_stream_toggle_returns_sse_scaffolding(self, example_app) -> None:
        """POST with stream=1 returns the user bubble + SSE-connected div."""
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/chat",
                method="POST",
                body=b"message=Hello&stream=1",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "msg-user" in response.text
            assert "Hello" in response.text
            assert "sse-connect" in response.text
            assert "/chat/stream" in response.text
            assert 'sse-close="done"' in response.text

    async def test_stream_no_toggle_returns_pending(self, example_app) -> None:
        """POST without stream field returns pending spinner, not SSE."""
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/chat",
                method="POST",
                body=b"message=Hello",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "msg-user" in response.text
            assert "/chat/complete" in response.text
            assert "sse-connect" not in response.text

    async def test_chat_stream_endpoint_simple(
        self, example_app, example_module, monkeypatch
    ) -> None:
        """GET /chat/stream streams tokens from the agent loop."""
        _install_llm_mock(
            monkeypatch,
            completes=[_openai_complete(content="")],
            stream_tokens=["Hello ", "world!"],
        )
        await _seed_user(example_module, "Hello")

        async with TestClient(example_app) as client:
            result = await client.sse("/chat/stream", max_events=5)

        assert result.status == 200
        fragments = [e for e in result.events if (e.event or "message") == "message"]
        text = "".join(e.data for e in fragments)
        assert "Hello" in text
        assert "world!" in text
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) == 1

    async def test_chat_stream_endpoint_with_tools(
        self, example_app, example_module, monkeypatch
    ) -> None:
        """GET /chat/stream handles tool rounds then streams the answer."""
        state = _install_llm_mock(
            monkeypatch,
            completes=[
                _openai_complete(tool_calls=[_tool_call("get_current_time")]),
                _openai_complete(content=""),
            ],
            stream_tokens=["It is ", "noon ", "UTC."],
        )
        await _seed_user(example_module, "What time is it?")

        async with TestClient(example_app) as client:
            result = await client.sse("/chat/stream", max_events=10)

        assert result.status == 200
        assert state["n"] == 2
        fragments = [e for e in result.events if (e.event or "message") == "message"]
        text = "".join(e.data for e in fragments)
        assert "noon" in text
        assert "UTC" in text

    async def test_chat_stream_endpoint_closes_with_done(
        self, example_app, example_module, monkeypatch
    ) -> None:
        """Stream always closes with a 'done' SSE event for sse-close."""
        _install_llm_mock(
            monkeypatch,
            completes=[_openai_complete(content="")],
            stream_tokens=["Why did the chicken ", "cross the road?"],
        )
        await _seed_user(example_module, "Tell me a joke")

        async with TestClient(example_app) as client:
            result = await client.sse("/chat/stream", max_events=5)

        assert result.status == 200
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) == 1
