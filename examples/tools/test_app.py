"""Tests for the MCP tools example."""

import json

from chirp.testing import TestClient


def _mcp(method: str, *, params: dict | None = None, rpc_id: int = 1) -> dict:
    """Build a JSON-RPC request body for MCP."""
    return {"jsonrpc": "2.0", "method": method, "id": rpc_id, "params": params or {}}


class TestRoutes:
    """Verify the HTTP routes still work alongside tools."""

    async def test_index_returns_json(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            data = json.loads(response.text)
            assert data["tool_count"] == 3
            assert data["notes"] == []


class TestMCPHandshake:
    """Verify the MCP initialize / tools/list flow."""

    async def test_initialize(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/mcp", json=_mcp("initialize"))
            assert response.status == 200
            body = json.loads(response.text)
            assert body["result"]["serverInfo"]["name"] == "chirp"
            assert "tools" in body["result"]["capabilities"]

    async def test_tools_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/mcp", json=_mcp("tools/list"))
            body = json.loads(response.text)
            tools = body["result"]["tools"]
            names = {t["name"] for t in tools}
            assert names == {"add_note", "list_notes", "search_notes"}

    async def test_tool_schemas_have_descriptions(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/mcp", json=_mcp("tools/list"))
            tools = json.loads(response.text)["result"]["tools"]
            for tool in tools:
                assert tool["description"], f"{tool['name']} missing description"
                assert tool["inputSchema"]["type"] == "object"


class TestToolCalls:
    """Verify tools can be called via MCP JSON-RPC."""

    async def test_add_and_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Add a note
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "add_note", "arguments": {"text": "Buy milk"}},
                ),
            )
            body = json.loads(response.text)
            content = json.loads(body["result"]["content"][0]["text"])
            assert content["text"] == "Buy milk"
            assert content["tag"] is None

            # List should contain the note
            response = await client.post(
                "/mcp",
                json=_mcp("tools/call", params={"name": "list_notes", "arguments": {}}),
            )
            body = json.loads(response.text)
            notes = json.loads(body["result"]["content"][0]["text"])
            assert len(notes) == 1
            assert notes[0]["text"] == "Buy milk"

    async def test_add_with_tag(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={
                        "name": "add_note",
                        "arguments": {"text": "Fix login bug", "tag": "work"},
                    },
                ),
            )
            body = json.loads(response.text)
            content = json.loads(body["result"]["content"][0]["text"])
            assert content["tag"] == "work"

    async def test_search(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Add two notes
            await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "add_note", "arguments": {"text": "Buy milk"}},
                ),
            )
            await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "add_note", "arguments": {"text": "Read book"}},
                ),
            )

            # Search should match only one
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "search_notes", "arguments": {"query": "milk"}},
                ),
            )
            body = json.loads(response.text)
            results = json.loads(body["result"]["content"][0]["text"])
            assert len(results) == 1
            assert results[0]["text"] == "Buy milk"

    async def test_unknown_tool_returns_error(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/mcp",
                json=_mcp(
                    "tools/call",
                    params={"name": "nope", "arguments": {}},
                ),
            )
            body = json.loads(response.text)
            assert "error" in body
            assert "not found" in body["error"]["message"].lower()
