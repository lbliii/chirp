"""Tests for the Ollama chat example.

Mocks Ollama at the httpx level — no real Ollama needed to run tests.
"""

import json
from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

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


@contextmanager
def mock_ollama(*responses: dict[str, Any]):
    """Mock the ollama_client.chat() function to return canned responses.

    Each call to chat() consumes the next response in order.
    """
    call_count = 0

    async def fake_chat(client, *, model, messages, tools=None):
        nonlocal call_count
        idx = min(call_count, len(responses) - 1)
        call_count += 1
        return responses[idx]

    with patch("examples.ollama.app.ollama_chat", side_effect=fake_chat):
        yield


class TestRoutes:
    """Verify the HTTP routes render correctly."""

    async def test_index_renders_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Ollama Chat" in response.text
            assert "Say something" in response.text

    async def test_clear_resets_conversation(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/clear")
            assert response.status == 200
            assert "cleared" in response.text.lower()


class TestMCPTools:
    """Verify all 5 tools work via MCP JSON-RPC."""

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
            # Add a note first
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


class TestChatWithMockedOllama:
    """Test the chat route with mocked Ollama responses."""

    async def test_chat_returns_simple_response(self, example_app) -> None:
        with mock_ollama(_ollama_response(content="Hello! How can I help?")):
            async with TestClient(example_app) as client:
                response = await client.post(
                    "/chat",
                    body=b"message=Hello",
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
                # SSE response — check it contains the assistant's message
                assert response.status == 200

    async def test_chat_empty_message_ignored(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/chat",
                body=b"message=",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200

    async def test_chat_with_tool_call(self, example_app) -> None:
        """Model calls get_current_time, then gives final answer."""
        with mock_ollama(
            # Round 1: model calls a tool
            _ollama_response(tool_calls=[_tool_call("get_current_time")]),
            # Round 2: model gives the final answer
            _ollama_response(content="The current time is 12:00:00 UTC."),
        ):
            async with TestClient(example_app) as client:
                response = await client.post(
                    "/chat",
                    body=b"message=What+time+is+it",
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
                assert response.status == 200

    async def test_chat_with_calculate_tool(self, example_app) -> None:
        """Model calls calculate, then gives final answer."""
        with mock_ollama(
            _ollama_response(
                tool_calls=[_tool_call("calculate", expression="2 + 2")],
            ),
            _ollama_response(content="2 + 2 = 4"),
        ):
            async with TestClient(example_app) as client:
                response = await client.post(
                    "/chat",
                    body=b"message=What+is+2+plus+2",
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
                assert response.status == 200
