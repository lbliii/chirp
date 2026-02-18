"""Tests for the Ollama chat example.

Mocks Ollama at the module level — no real Ollama needed to run tests.
"""

import json
from typing import Any

from chirp.testing import TestClient


def _mcp(method: str, *, params: dict | None = None, rpc_id: int = 1) -> dict:
    """Build a JSON-RPC request body for MCP."""
    return {"jsonrpc": "2.0", "method": method, "id": rpc_id, "params": params or {}}


def _ollama_response(
    content: str = "",
    tool_calls: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a mock Ollama /api/chat response."""
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"model": "llama3.2", "message": msg, "done": True}


def _tool_call(name: str, **arguments: Any) -> dict[str, Any]:
    """Build a single Ollama tool_call object."""
    return {"function": {"name": name, "arguments": arguments}}


def _fake_chat_from(*responses):
    """Create a fake ollama_chat function from a sequence of responses."""
    state = {"count": 0}

    async def fake_chat(client, *, model, messages, tools=None):
        idx = min(state["count"], len(responses) - 1)
        state["count"] += 1
        return responses[idx]

    return fake_chat, state


def _fake_stream(*tokens):
    """Create a fake ollama_chat_stream that yields the given tokens."""

    async def fake_stream_fn(client, *, model, messages):
        for token in tokens:
            yield token

    return fake_stream_fn


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

    async def test_index_falls_back_without_ollama(self, example_app) -> None:
        """When Ollama is unreachable, the index still renders with a static badge."""
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
    """Test the non-streaming chat path (stream toggle OFF)."""

    async def test_chat_returns_response(self, example_app, example_module) -> None:
        fake_chat, state = _fake_chat_from(
            _ollama_response(content="Hello! How can I help?"),
        )
        example_module.ollama_chat = fake_chat

        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=Hello",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "Hello! How can I help?" in response.text
            assert state["count"] == 1

    async def test_chat_empty_message_ignored(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200

    async def test_chat_with_tool_call(self, example_app, example_module) -> None:
        fake_chat, state = _fake_chat_from(
            _ollama_response(tool_calls=[_tool_call("get_current_time")]),
            _ollama_response(content="It is currently 12:00 UTC."),
        )
        example_module.ollama_chat = fake_chat

        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=What+time+is+it",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "12:00 UTC" in response.text
            assert state["count"] == 2

    async def test_chat_with_calculate_tool(self, example_app, example_module) -> None:
        fake_chat, state = _fake_chat_from(
            _ollama_response(tool_calls=[_tool_call("calculate", expression="2 + 2")]),
            _ollama_response(content="2 + 2 = 4"),
        )
        example_module.ollama_chat = fake_chat

        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=What+is+2+plus+2",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "2 + 2 = 4" in response.text
            assert state["count"] == 2

    async def test_chat_tool_results_sent_back(self, example_app, example_module) -> None:
        captured_messages: list[list[dict]] = []

        responses = [
            _ollama_response(
                tool_calls=[_tool_call("add_note", text="Remember this")],
            ),
            _ollama_response(content="Done! I added the note."),
        ]
        call_count = 0

        async def fake_chat(client, *, model, messages, tools=None):
            nonlocal call_count
            captured_messages.append(list(messages))
            idx = min(call_count, len(responses) - 1)
            call_count += 1
            return responses[idx]

        example_module.ollama_chat = fake_chat

        async with TestClient(example_app) as client:
            await client.post(
                "/chat",
                body=b"message=Remember+this",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )

        assert len(captured_messages) == 2
        second_call_msgs = captured_messages[1]
        tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "Remember this" in tool_msgs[0]["content"]

    async def test_chat_shows_tools_used(self, example_app, example_module) -> None:
        fake_chat, _ = _fake_chat_from(
            _ollama_response(tool_calls=[_tool_call("get_current_time")]),
            _ollama_response(content="It is noon."),
        )
        example_module.ollama_chat = fake_chat

        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=What+time",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert "get_current_time" in response.text


# -------------------------------------------------------------------------
# Streaming chat tests
# -------------------------------------------------------------------------


class TestChatStreaming:
    """Test the streaming chat path (stream toggle ON)."""

    async def test_stream_toggle_returns_sse_scaffolding(self, example_app) -> None:
        """POST with stream=1 returns the user bubble + SSE-connected div."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=Hello&stream=1",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "msg-user" in response.text
            assert "Hello" in response.text
            assert "sse-connect" in response.text
            assert "/chat/stream" in response.text
            assert 'sse-close="done"' in response.text

    async def test_stream_no_toggle_returns_full_response(
        self, example_app, example_module
    ) -> None:
        """POST without stream field returns the complete response."""
        fake_chat, _ = _fake_chat_from(
            _ollama_response(content="Full response here."),
        )
        example_module.ollama_chat = fake_chat

        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=Hello",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "Full response here." in response.text
            assert "sse-connect" not in response.text

    async def test_chat_stream_endpoint_simple(self, example_app, example_module) -> None:
        """GET /chat/stream streams tokens via ollama_chat_stream."""
        example_module._append_history("user", "Hello")

        # Phase 1: non-streaming probe — no tool calls (response discarded)
        fake_chat, _ = _fake_chat_from(
            _ollama_response(content="(discarded)"),
        )
        example_module.ollama_chat = fake_chat
        # Phase 2: streaming delivers the actual tokens
        example_module.ollama_chat_stream = _fake_stream("Hi ", "there!")

        async with TestClient(example_app) as client:
            result = await client.sse("/chat/stream", max_events=5)

        assert result.status == 200
        fragments = [e for e in result.events if e.event == "fragment"]
        text = "".join(e.data for e in fragments)
        assert "Hi " in text
        assert "there!" in text
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) == 1

    async def test_chat_stream_endpoint_with_tools(self, example_app, example_module) -> None:
        """GET /chat/stream handles tool rounds then streams the answer."""
        example_module._append_history("user", "What time is it?")

        # Phase 1: tool round + no-tool probe (response discarded)
        fake_chat, state = _fake_chat_from(
            _ollama_response(tool_calls=[_tool_call("get_current_time")]),
            _ollama_response(content="(discarded)"),
        )
        example_module.ollama_chat = fake_chat
        # Phase 2: streaming delivers the answer
        example_module.ollama_chat_stream = _fake_stream("It is ", "noon ", "UTC.")

        async with TestClient(example_app) as client:
            result = await client.sse("/chat/stream", max_events=10)

        assert result.status == 200
        # Model made 2 non-streaming calls: tool round + probe
        assert state["count"] == 2
        fragments = [e for e in result.events if e.event == "fragment"]
        text = "".join(e.data for e in fragments)
        assert "noon" in text
        assert "UTC" in text

    async def test_chat_stream_endpoint_closes_with_done(self, example_app, example_module) -> None:
        """Stream always closes with a 'done' SSE event for sse-close."""
        example_module._append_history("user", "Tell me a joke")

        fake_chat, _ = _fake_chat_from(
            _ollama_response(content="(discarded)"),
        )
        example_module.ollama_chat = fake_chat
        example_module.ollama_chat_stream = _fake_stream("Why did the chicken ", "cross the road?")

        async with TestClient(example_app) as client:
            result = await client.sse("/chat/stream", max_events=5)

        assert result.status == 200
        done_events = [e for e in result.events if e.event == "done"]
        assert len(done_events) == 1
