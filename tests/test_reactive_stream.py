"""Integration tests for reactive_stream.

Covers the full test matrix:

- Emitted event yields correct Fragment(s) for affected blocks
- Origin filtering: events with matching origin are skipped
- Context builder failure: logged, stream continues
- Context builder returns non-dict: logged, skipped
- No affected blocks for a change: no Fragment yielded
- Multiple blocks affected: all yielded in order
"""

import asyncio
import logging

import pytest

from chirp.pages.reactive import BlockRef, ChangeEvent, DependencyIndex, ReactiveBus
from chirp.pages.reactive.stream import reactive_stream
from chirp.templating.returns import Fragment


def _make_index(*blocks: tuple[str, str, list[str]]) -> DependencyIndex:
    """Build a DependencyIndex from (template, block, [dep_paths]) tuples.

    Bypasses kida — registers blocks directly into internal mappings.
    """
    index = DependencyIndex()
    for template, block, dep_paths in blocks:
        ref = BlockRef(template_name=template, block_name=block)
        for path in dep_paths:
            index._path_to_blocks.setdefault(path, []).append(ref)
            parts = path.split(".")
            for i in range(len(parts)):
                prefix = ".".join(parts[: i + 1])
                index._prefix_to_paths.setdefault(prefix, set()).add(path)
    return index


async def _collect_fragments(
    bus: ReactiveBus,
    stream_result: object,
    *,
    max_fragments: int = 10,
    timeout: float = 1.0,
) -> list[Fragment]:
    """Drain fragments from an EventStream's generator."""
    # EventStream wraps an async generator; access it directly
    gen = stream_result.generator  # type: ignore[attr-defined]
    fragments: list[Fragment] = []
    try:
        async with asyncio.timeout(timeout):
            async for fragment in gen:
                fragments.append(fragment)
                if len(fragments) >= max_fragments:
                    break
    except TimeoutError:
        pass
    return fragments


# ---------------------------------------------------------------------------
# Basic fragment yield
# ---------------------------------------------------------------------------


class TestBasicFragmentYield:
    """Emitted events produce correct Fragment objects."""

    async def test_single_block_yields_fragment(self) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "task_list", ["tasks"]))

        stream = reactive_stream(
            bus,
            scope="board:1",
            index=index,
            context_builder=lambda: {"tasks": ["a", "b"]},
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)
        await bus.emit(ChangeEvent(scope="board:1", changed_paths=frozenset({"tasks"})))
        fragments = await task

        assert len(fragments) == 1
        assert fragments[0].template_name == "page.html"
        assert fragments[0].block_name == "task_list"

    async def test_fragment_receives_context(self) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "count", ["total"]))

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=lambda: {"total": 42},
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)
        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"total"})))
        fragments = await task

        assert len(fragments) == 1
        assert fragments[0].context["total"] == 42


# ---------------------------------------------------------------------------
# Multiple blocks affected
# ---------------------------------------------------------------------------


class TestMultipleBlocks:
    """When a change affects multiple blocks, all are yielded."""

    async def test_two_blocks_from_one_event(self) -> None:
        bus = ReactiveBus()
        index = _make_index(
            ("page.html", "task_list", ["tasks"]),
            ("page.html", "task_count", ["tasks"]),
        )

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=lambda: {"tasks": []},
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=2))
        await asyncio.sleep(0.01)
        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"tasks"})))
        fragments = await task

        assert len(fragments) == 2
        block_names = {f.block_name for f in fragments}
        assert block_names == {"task_list", "task_count"}


# ---------------------------------------------------------------------------
# Origin filtering
# ---------------------------------------------------------------------------


class TestOriginFiltering:
    """Events from the same origin are skipped."""

    async def test_same_origin_skipped(self) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "content", ["data"]))

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=lambda: {"data": "x"},
            origin="user-123",
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1, timeout=0.3))
        await asyncio.sleep(0.01)
        # Emit with same origin — should be skipped
        await bus.emit(
            ChangeEvent(
                scope="s",
                changed_paths=frozenset({"data"}),
                origin="user-123",
            )
        )
        fragments = await task
        assert len(fragments) == 0

    async def test_different_origin_delivered(self) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "content", ["data"]))

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=lambda: {"data": "x"},
            origin="user-123",
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)
        # Emit with different origin — should be delivered
        await bus.emit(
            ChangeEvent(
                scope="s",
                changed_paths=frozenset({"data"}),
                origin="user-456",
            )
        )
        fragments = await task
        assert len(fragments) == 1

    async def test_none_origin_always_delivered(self) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "content", ["data"]))

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=lambda: {"data": "x"},
            origin="user-123",
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)
        # System event (origin=None) always delivered
        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"data"}), origin=None))
        fragments = await task
        assert len(fragments) == 1


# ---------------------------------------------------------------------------
# No affected blocks
# ---------------------------------------------------------------------------


class TestNoAffectedBlocks:
    """When a change doesn't affect any blocks, no fragment is yielded."""

    async def test_unrelated_change_yields_nothing(self) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "task_list", ["tasks"]))

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=lambda: {"tasks": []},
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1, timeout=0.3))
        await asyncio.sleep(0.01)
        # "users" path doesn't match any registered block
        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"users"})))
        fragments = await task
        assert len(fragments) == 0


# ---------------------------------------------------------------------------
# Context builder errors
# ---------------------------------------------------------------------------


class TestContextBuilderErrors:
    """Context builder failures are logged and the stream continues."""

    async def test_exception_logged_and_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "content", ["data"]))

        call_count = 0

        def flaky_context() -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("db connection lost")
            return {"data": "recovered"}

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=flaky_context,
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)

        with caplog.at_level(logging.ERROR, logger="chirp.reactive"):
            # First emit — context builder raises, event skipped
            await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"data"})))
            await asyncio.sleep(0.05)

        # Second emit — context builder succeeds
        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"data"})))
        fragments = await task

        assert len(fragments) == 1
        assert fragments[0].context["data"] == "recovered"
        assert "context_builder failed" in caplog.text

    async def test_non_dict_return_logged_and_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "content", ["data"]))

        call_count = 0

        def bad_then_good() -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not a dict"  # type: ignore[return-value]
            return {"data": "ok"}

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=bad_then_good,
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)

        with caplog.at_level(logging.WARNING, logger="chirp.reactive"):
            await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"data"})))
            await asyncio.sleep(0.05)

        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"data"})))
        fragments = await task

        assert len(fragments) == 1
        assert "must return dict" in caplog.text


# ---------------------------------------------------------------------------
# Async context builder
# ---------------------------------------------------------------------------


class TestAsyncContextBuilder:
    """Context builder can be an async function."""

    async def test_async_context_builder(self) -> None:
        bus = ReactiveBus()
        index = _make_index(("page.html", "content", ["data"]))

        async def async_context() -> dict:
            await asyncio.sleep(0.001)
            return {"data": "async-value"}

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=async_context,
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)
        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"data"})))
        fragments = await task

        assert len(fragments) == 1
        assert fragments[0].context["data"] == "async-value"


# ---------------------------------------------------------------------------
# DOM target passthrough
# ---------------------------------------------------------------------------


class TestDOMTarget:
    """BlockRef.target_id is passed through as fragment target."""

    async def test_dom_id_used_as_target(self) -> None:
        bus = ReactiveBus()
        index = DependencyIndex()
        ref = BlockRef(template_name="page.html", block_name="count", dom_id="task-count")
        index._path_to_blocks.setdefault("total", []).append(ref)
        index._prefix_to_paths.setdefault("total", set()).add("total")

        stream = reactive_stream(
            bus,
            scope="s",
            index=index,
            context_builder=lambda: {"total": 5},
        )

        task = asyncio.create_task(_collect_fragments(bus, stream, max_fragments=1))
        await asyncio.sleep(0.01)
        await bus.emit(ChangeEvent(scope="s", changed_paths=frozenset({"total"})))
        fragments = await task

        assert len(fragments) == 1
        assert fragments[0].target == "task-count"
