"""MCP client — consume remote toolsets and merge into a local registry."""

from __future__ import annotations

import json
from typing import Any

from chirp.tools.registry import McpToolInfo, ToolDef, ToolRegistry


class MCPClient:
    """HTTP JSON-RPC client for a remote MCP server's tool surface."""

    __slots__ = ("_headers", "_registry", "_url")

    def __init__(
        self,
        url: str,
        /,
        *,
        headers: dict[str, str] | None = None,
        auth_token: str | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._headers = dict(headers or {})
        if auth_token:
            self._headers.setdefault("Authorization", f"Bearer {auth_token}")
        self._headers.setdefault("Content-Type", "application/json")
        self._registry: ToolRegistry | None = None

    async def list_tools(self) -> list[McpToolInfo]:
        result = await self._rpc("tools/list", {})
        tools = result.get("tools") or []
        return [
            McpToolInfo(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema") or {"type": "object", "properties": {}},
            )
            for t in tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        content = result.get("content") or []
        if not content:
            return result
        block = content[0]
        if block.get("type") == "text":
            text = block.get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return result

    def merge_into(self, registry: ToolRegistry, *, prefix: str = "remote") -> ToolRegistry:
        """Return a new registry with remote tools as namespaced proxies."""
        if self._registry is None:
            msg = "Call connect() before merge_into()"
            raise RuntimeError(msg)
        return self._registry

    async def connect(self, registry: ToolRegistry, *, prefix: str = "remote") -> ToolRegistry:
        """Fetch remote tools and build a merged registry."""
        remote_tools = await self.list_tools()
        client = self

        def _make_handler(name: str):
            async def handler(**kwargs: Any) -> Any:
                return await client.call_tool(name, kwargs)

            return handler

        extras: list[ToolDef] = []
        for info in remote_tools:
            remote_name = info["name"]
            local_name = f"{prefix}__{remote_name}" if prefix else remote_name
            extras.append(
                ToolDef(
                    name=local_name,
                    description=info["description"],
                    handler=_make_handler(remote_name),
                    schema=info["inputSchema"],
                )
            )

        merged = registry.with_tools(extras)
        self._registry = merged
        return merged

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        from chirp.ai._providers import _get_httpx

        httpx = _get_httpx()
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._url,
                json=payload,
                headers=self._headers,
                timeout=60.0,
            )
        if response.status_code != 200:
            msg = f"MCP request failed: HTTP {response.status_code}"
            raise RuntimeError(msg)
        data = response.json()
        if "error" in data:
            err = data["error"]
            msg = err.get("message", "MCP error")
            raise RuntimeError(msg)
        result = data.get("result")
        if not isinstance(result, dict):
            msg = "Invalid MCP response"
            raise TypeError(msg)
        return result
