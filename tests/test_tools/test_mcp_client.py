"""Tests for MCP client tool merge."""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("httpx")

from chirp.tools.client import MCPClient
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import ToolRegistry


def _install_mock_transport(monkeypatch: pytest.MonkeyPatch, responses: list[dict]) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body.get("method")
        if method == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": responses[0]})
        if method == "tools/call":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": responses[1]})
        return httpx.Response(400, json={"error": "unknown method"})

    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)


@pytest.mark.issue(434)
class TestMCPClient:
    @pytest.mark.asyncio
    async def test_merge_remote_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_mock_transport(
            monkeypatch,
            [
                {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"q": {"type": "string"}},
                            },
                        }
                    ]
                },
                {"content": [{"type": "text", "text": "ok"}]},
            ],
        )
        bus = ToolEventBus()
        local = ToolRegistry([], bus)
        client = MCPClient("http://mcp.test/mcp")
        merged = await client.connect(local, prefix="remote")
        names = [t["name"] for t in merged.list_tools()]
        assert "remote__search" in names
        result = await merged.call_tool("remote__search", {"q": "hi"})
        assert result == "ok"
