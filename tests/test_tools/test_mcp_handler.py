"""Tests for chirp.tools.handler — MCP JSON-RPC protocol handler."""

import json

import pytest

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.tools.events import ToolEventBus
from chirp.tools.handler import handle_mcp_request
from chirp.tools.registry import ToolRegistry, compile_tools


def _make_request(
    *,
    method: str = "POST",
    path: str = "/mcp",
    body: dict | bytes | None = None,
) -> Request:
    """Build a chirp Request for MCP handler tests."""
    if isinstance(body, dict):
        raw_body = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        raw_body = body
    else:
        raw_body = b""

    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": raw_body, "more_body": False}
        return {"type": "http.disconnect"}

    return Request.from_asgi(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        },
        receive,
    )


def _parse_response(response: Response) -> tuple[int, dict]:
    """Extract status and JSON body from a chirp Response."""
    body_bytes = response.body_bytes
    body = json.loads(body_bytes) if body_bytes else {}
    return response.status, body


class TestMCPHandler:
    """Test the MCP JSON-RPC protocol handler at the Request/Response level."""

    def _make_registry(self) -> ToolRegistry:
        async def search(query: str, limit: int = 10) -> list[dict]:
            return [{"name": "item", "query": query, "limit": limit}]

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        return compile_tools(
            [
                ("search", "Search items", search),
                ("greet", "Greet someone", greet),
            ],
            ToolEventBus(),
        )

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}},
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["id"] == 1
        assert "protocolVersion" in body["result"]
        assert "capabilities" in body["result"]
        assert "tools" in body["result"]["capabilities"]

    @pytest.mark.asyncio
    async def test_tools_list(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={"jsonrpc": "2.0", "method": "tools/list", "id": 2, "params": {}},
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        tools = body["result"]["tools"]
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"search", "greet"}

    @pytest.mark.asyncio
    async def test_tools_list_schema(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={"jsonrpc": "2.0", "method": "tools/list", "id": 3, "params": {}},
        )
        response = await handle_mcp_request(request, registry)
        _status, body = _parse_response(response)
        tools = body["result"]["tools"]
        search_tool = next(t for t in tools if t["name"] == "search")
        schema = search_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"] == {"type": "string"}

    @pytest.mark.asyncio
    async def test_tools_call(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 4,
                "params": {"name": "greet", "arguments": {"name": "World"}},
            }
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert body["id"] == 4
        content = body["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Hello, World!"

    @pytest.mark.asyncio
    async def test_tools_call_async(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 5,
                "params": {"name": "search", "arguments": {"query": "test"}},
            }
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        content = body["result"]["content"]
        result = json.loads(content[0]["text"])
        assert result == [{"name": "item", "query": "test", "limit": 10}]

    @pytest.mark.asyncio
    async def test_tools_call_not_found(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 6,
                "params": {"name": "missing", "arguments": {}},
            }
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert "error" in body
        assert body["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_method_not_found(self) -> None:
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "unknown/method",
                "id": 7,
                "params": {},
            }
        )
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 200
        assert "error" in body
        assert body["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        registry = self._make_registry()
        request = _make_request(body=b"not json{{{")
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_empty_body(self) -> None:
        registry = self._make_registry()
        request = _make_request(body=b"")
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32700

    @pytest.mark.asyncio
    async def test_get_method_rejected(self) -> None:
        registry = self._make_registry()
        request = _make_request(method="GET")
        response = await handle_mcp_request(request, registry)
        assert response.status == 405

    @pytest.mark.asyncio
    async def test_missing_rpc_method(self) -> None:
        registry = self._make_registry()
        request = _make_request(body={"jsonrpc": "2.0", "id": 8})
        response = await handle_mcp_request(request, registry)
        status, body = _parse_response(response)
        assert status == 400
        assert body["error"]["code"] == -32600

    @pytest.mark.asyncio
    async def test_notifications_initialized(self) -> None:
        """notifications/initialized has no id — server returns 204."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                # No "id" — this is a JSON-RPC notification
            }
        )
        response = await handle_mcp_request(request, registry)
        assert response.status == 204

    @pytest.mark.asyncio
    async def test_notification_unknown_method(self) -> None:
        """Any notification (no id) gets 204, even for unknown methods."""
        registry = self._make_registry()
        request = _make_request(
            body={
                "jsonrpc": "2.0",
                "method": "notifications/something_else",
            }
        )
        response = await handle_mcp_request(request, registry)
        assert response.status == 204
