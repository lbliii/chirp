"""Tests for chirp.tools.events — ToolEventBus, ToolRegistryEvents."""

import asyncio
import time

import pytest

from chirp.tools.events import ToolCallEvent, ToolEventBus
from chirp.tools.registry import compile_tools


class TestToolEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self) -> None:
        bus = ToolEventBus()
        received: list[ToolCallEvent] = []

        async def collector():
            async for event in bus.subscribe():
                received.append(event)
                if len(received) >= 2:
                    break

        event1 = ToolCallEvent(
            tool_name="search",
            arguments={"q": "test"},
            result=[],
            timestamp=time.time(),
        )
        event2 = ToolCallEvent(
            tool_name="create",
            arguments={"title": "hi"},
            result={"id": 1},
            timestamp=time.time(),
        )

        task = asyncio.create_task(collector())
        # Give the subscriber time to register
        await asyncio.sleep(0.01)

        await bus.emit(event1)
        await bus.emit(event2)

        await asyncio.wait_for(task, timeout=2.0)
        assert len(received) == 2
        assert received[0].tool_name == "search"
        assert received[1].tool_name == "create"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        bus = ToolEventBus()
        received_a: list[ToolCallEvent] = []
        received_b: list[ToolCallEvent] = []

        async def collector_a():
            async for event in bus.subscribe():
                received_a.append(event)
                if len(received_a) >= 1:
                    break

        async def collector_b():
            async for event in bus.subscribe():
                received_b.append(event)
                if len(received_b) >= 1:
                    break

        task_a = asyncio.create_task(collector_a())
        task_b = asyncio.create_task(collector_b())
        await asyncio.sleep(0.01)

        event = ToolCallEvent(
            tool_name="test",
            arguments={},
            result="ok",
            timestamp=time.time(),
        )
        await bus.emit(event)

        await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=2.0)
        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        bus = ToolEventBus()
        count = 0

        async def collector():
            nonlocal count
            async for _event in bus.subscribe():
                count += 1

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        bus.close()
        await asyncio.wait_for(task, timeout=2.0)
        assert count == 0

    def test_event_frozen(self) -> None:
        event = ToolCallEvent(
            tool_name="test",
            arguments={},
            result="ok",
            timestamp=1234.0,
        )
        with pytest.raises(AttributeError):
            event.tool_name = "other"  # type: ignore[misc]

    def test_event_call_id_generated(self) -> None:
        event = ToolCallEvent(
            tool_name="test",
            arguments={},
            result="ok",
            timestamp=1234.0,
        )
        assert isinstance(event.call_id, str)
        assert len(event.call_id) == 12


class TestToolRegistryEvents:
    @pytest.mark.asyncio
    async def test_call_emits_event(self) -> None:
        bus = ToolEventBus()
        received: list[ToolCallEvent] = []

        async def search(query: str) -> list[str]:
            return ["result1"]

        registry = compile_tools([("search", "Search", search)], bus)

        async def collector():
            async for event in bus.subscribe():
                received.append(event)
                break

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)

        result = await registry.call_tool("search", {"query": "test"})
        assert result == ["result1"]

        await asyncio.wait_for(task, timeout=2.0)
        assert len(received) == 1
        assert received[0].tool_name == "search"
        assert received[0].arguments == {"query": "test"}
        assert received[0].result == ["result1"]
