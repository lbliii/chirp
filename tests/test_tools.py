"""Tests for the MCP tools system — ToolRegistry, ToolDef, ToolEventBus, schema generation."""

import asyncio
import time

import pytest

from chirp.tools.events import ToolCallEvent, ToolEventBus
from chirp.tools.registry import ToolDef, ToolRegistry, compile_tools
from chirp.tools.schema import function_to_schema

# ---------------------------------------------------------------------------
# ToolDef
# ---------------------------------------------------------------------------


class TestToolDef:
    def test_frozen(self) -> None:
        td = ToolDef(name="t", description="d", handler=lambda: None, schema={})
        with pytest.raises(AttributeError):
            td.name = "x"  # type: ignore[misc]

    def test_fields(self) -> None:
        def handler(x: str) -> str:
            return x

        td = ToolDef(name="echo", description="Echo", handler=handler, schema={"type": "object"})
        assert td.name == "echo"
        assert td.description == "Echo"
        assert td.handler is handler


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def _make_registry(self) -> ToolRegistry:
        bus = ToolEventBus()

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        async def add(a: int, b: int) -> int:
            return a + b

        return compile_tools(
            [
                ("greet", "Greet someone", greet),
                ("add", "Add two numbers", add),
            ],
            bus,
        )

    def test_list_tools(self) -> None:
        registry = self._make_registry()
        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"greet", "add"}
        for t in tools:
            assert "inputSchema" in t
            assert "description" in t

    def test_get(self) -> None:
        registry = self._make_registry()
        assert registry.get("greet") is not None
        assert registry.get("nonexistent") is None

    def test_contains(self) -> None:
        registry = self._make_registry()
        assert "greet" in registry
        assert "nonexistent" not in registry

    def test_len(self) -> None:
        registry = self._make_registry()
        assert len(registry) == 2

    @pytest.mark.asyncio
    async def test_call_sync_tool(self) -> None:
        registry = self._make_registry()
        result = await registry.call_tool("greet", {"name": "World"})
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_call_async_tool(self) -> None:
        registry = self._make_registry()
        result = await registry.call_tool("add", {"a": 3, "b": 4})
        assert result == 7

    @pytest.mark.asyncio
    async def test_call_unknown_tool_raises(self) -> None:
        registry = self._make_registry()
        with pytest.raises(KeyError, match="not found"):
            await registry.call_tool("unknown", {})

    def test_duplicate_name_raises(self) -> None:
        bus = ToolEventBus()
        with pytest.raises(ValueError, match="Duplicate"):
            compile_tools(
                [
                    ("dup", "First", lambda: None),
                    ("dup", "Second", lambda: None),
                ],
                bus,
            )


# ---------------------------------------------------------------------------
# ToolEventBus
# ---------------------------------------------------------------------------


class TestToolEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self) -> None:
        bus = ToolEventBus()
        received: list[ToolCallEvent] = []

        async def subscriber() -> None:
            async for event in bus.subscribe():
                received.append(event)
                if len(received) >= 2:
                    break

        event1 = ToolCallEvent(tool_name="t1", arguments={}, result="r1", timestamp=time.time())
        event2 = ToolCallEvent(tool_name="t2", arguments={}, result="r2", timestamp=time.time())

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)
        await bus.emit(event1)
        await bus.emit(event2)
        await asyncio.wait_for(task, timeout=2.0)

        assert len(received) == 2
        assert received[0].tool_name == "t1"
        assert received[1].tool_name == "t2"

    @pytest.mark.asyncio
    async def test_close_stops_subscribers(self) -> None:
        bus = ToolEventBus()
        received: list[ToolCallEvent] = []

        async def subscriber() -> None:
            received.extend([event async for event in bus.subscribe()])

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)
        bus.close()
        await asyncio.wait_for(task, timeout=2.0)
        assert received == []

    def test_call_event_frozen(self) -> None:
        event = ToolCallEvent(tool_name="t", arguments={}, result=None, timestamp=0.0)
        with pytest.raises(AttributeError):
            event.tool_name = "x"  # type: ignore[misc]

    def test_call_event_auto_id(self) -> None:
        event = ToolCallEvent(tool_name="t", arguments={}, result=None, timestamp=0.0)
        assert isinstance(event.call_id, str)
        assert len(event.call_id) == 12


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------


class TestFunctionToSchema:
    def test_basic_types(self) -> None:
        def func(name: str, age: int, score: float, active: bool) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["type"] == "object"
        assert schema["properties"]["name"] == {"type": "string"}
        assert schema["properties"]["age"] == {"type": "integer"}
        assert schema["properties"]["score"] == {"type": "number"}
        assert schema["properties"]["active"] == {"type": "boolean"}
        assert set(schema["required"]) == {"name", "age", "score", "active"}

    def test_optional_param(self) -> None:
        def func(name: str, tag: str | None = None) -> None:
            pass

        schema = function_to_schema(func)
        assert "name" in schema["properties"]
        assert "tag" in schema["properties"]
        assert schema["required"] == ["name"]

    def test_default_value_not_required(self) -> None:
        def func(name: str, limit: int = 10) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["required"] == ["name"]

    def test_list_type(self) -> None:
        def func(items: list[str]) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["items"] == {"type": "array", "items": {"type": "string"}}

    def test_request_param_excluded(self) -> None:
        from chirp.http.request import Request

        def func(request: Request, name: str) -> None:
            pass

        schema = function_to_schema(func)
        assert "request" not in schema["properties"]
        assert schema["required"] == ["name"]

    def test_unannotated_defaults_to_string(self) -> None:
        def func(x) -> None:
            pass

        schema = function_to_schema(func)
        assert schema["properties"]["x"] == {"type": "string"}
