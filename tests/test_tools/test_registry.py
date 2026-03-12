"""Tests for chirp.tools.registry — ToolDef, ToolRegistry, compile_tools."""

from typing import Any

import pytest

from chirp.tools.events import ToolEventBus
from chirp.tools.registry import ToolDef, ToolRegistry, compile_tools


class TestToolDef:
    def test_frozen(self) -> None:
        def handler() -> str:
            return "ok"

        tool = ToolDef(name="test", description="A test", handler=handler, schema={})
        with pytest.raises(AttributeError):
            tool.name = "other"  # type: ignore[misc]

    def test_fields(self) -> None:
        def handler() -> str:
            return "ok"

        tool = ToolDef(
            name="search",
            description="Search things",
            handler=handler,
            schema={"type": "object", "properties": {}},
        )
        assert tool.name == "search"
        assert tool.description == "Search things"
        assert tool.handler is handler


class TestToolRegistry:
    def _make_registry(
        self,
        tools: list[tuple[str, str, Any]] | None = None,
    ) -> ToolRegistry:
        bus = ToolEventBus()
        if tools is None:
            tools = [
                ("search", "Search items", self._search_handler),
                ("create", "Create item", self._create_handler),
            ]
        return compile_tools(tools, bus)

    async def _search_handler(self, query: str) -> list[dict]:
        return [{"name": "item1", "query": query}]

    async def _create_handler(self, title: str, body: str = "") -> dict:
        return {"title": title, "body": body}

    def test_list_tools(self) -> None:
        registry = self._make_registry()
        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"search", "create"}

    def test_list_tools_format(self) -> None:
        registry = self._make_registry()
        tools = registry.list_tools()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    def test_contains(self) -> None:
        registry = self._make_registry()
        assert "search" in registry
        assert "missing" not in registry

    def test_len(self) -> None:
        registry = self._make_registry()
        assert len(registry) == 2

    def test_get(self) -> None:
        registry = self._make_registry()
        tool = registry.get("search")
        assert tool is not None
        assert tool.name == "search"

    def test_get_missing(self) -> None:
        registry = self._make_registry()
        assert registry.get("nope") is None

    @pytest.mark.asyncio
    async def test_call_tool(self) -> None:
        async def search(query: str) -> list[dict]:
            return [{"q": query}]

        registry = self._make_registry([("search", "Search", search)])
        result = await registry.call_tool("search", {"query": "test"})
        assert result == [{"q": "test"}]

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self) -> None:
        registry = self._make_registry([])
        with pytest.raises(KeyError, match="Tool not found"):
            await registry.call_tool("missing", {})

    @pytest.mark.asyncio
    async def test_call_sync_tool(self) -> None:
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        registry = self._make_registry([("greet", "Greet", greet)])
        result = await registry.call_tool("greet", {"name": "World"})
        assert result == "Hello, World!"

    def test_duplicate_name_raises(self) -> None:
        def handler() -> str:
            return "ok"

        with pytest.raises(ValueError, match="Duplicate tool name"):
            compile_tools(
                [("test", "Test", handler), ("test", "Test 2", handler)],
                ToolEventBus(),
            )
