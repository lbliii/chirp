"""Integration tests for ReactiveBus.

Covers the full test matrix:

- Single subscriber receives emitted events
- Multiple subscribers on same scope
- Scope isolation (different scopes don't cross-talk)
- close(scope) sends sentinel, subscriber exits
- close() (all scopes) sends sentinel to all
- Back-pressure: full queue drops events silently
- Cleanup: subscriber exit removes queue from internal state
- Empty scope (no subscribers) is a no-op
- Thread safety: emit_sync from a thread, subscribe from async
"""

import asyncio
import threading

from chirp.pages.reactive import ChangeEvent, ReactiveBus


def _event(scope: str = "s", paths: str | set[str] = "x") -> ChangeEvent:
    """Shorthand for creating a ChangeEvent."""
    if isinstance(paths, str):
        paths = {paths}
    return ChangeEvent(scope=scope, changed_paths=frozenset(paths))


# ---------------------------------------------------------------------------
# Single subscriber
# ---------------------------------------------------------------------------


class TestSingleSubscriber:
    """One subscriber receives events emitted to its scope."""

    async def test_receives_emitted_event(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for event in bus.subscribe("s"):
                received.append(event)
                break  # just take one

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)
        await bus.emit(_event("s"))
        await asyncio.sleep(0.01)
        bus.close("s")
        await task
        assert len(received) == 1
        assert received[0].scope == "s"

    async def test_receives_multiple_events(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for event in bus.subscribe("s"):
                received.append(event)
                if len(received) == 3:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)
        for i in range(3):
            await bus.emit(_event("s", f"path.{i}"))
        await task
        assert len(received) == 3

    async def test_changed_paths_preserved(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for event in bus.subscribe("s"):
                received.append(event)
                break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)
        await bus.emit(_event("s", {"a.b", "c.d"}))
        await task
        assert received[0].changed_paths == frozenset({"a.b", "c.d"})


# ---------------------------------------------------------------------------
# Multiple subscribers
# ---------------------------------------------------------------------------


class TestMultipleSubscribers:
    """All subscribers on the same scope receive the event."""

    async def test_both_receive(self) -> None:
        bus = ReactiveBus()
        received_a: list[ChangeEvent] = []
        received_b: list[ChangeEvent] = []

        async def collect(target: list[ChangeEvent]) -> None:
            async for event in bus.subscribe("s"):
                target.append(event)
                break

        task_a = asyncio.create_task(collect(received_a))
        task_b = asyncio.create_task(collect(received_b))
        await asyncio.sleep(0.01)
        await bus.emit(_event("s"))
        await asyncio.gather(task_a, task_b)
        assert len(received_a) == 1
        assert len(received_b) == 1


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------


class TestScopeIsolation:
    """Events on one scope do not reach subscribers of another scope."""

    async def test_different_scope_not_received(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for event in bus.subscribe("scope-a"):
                received.append(event)
                break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)
        # Emit to a different scope
        await bus.emit(_event("scope-b"))
        await asyncio.sleep(0.05)
        # The collector should still be waiting — close to unblock
        bus.close("scope-a")
        await task
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Close behavior
# ---------------------------------------------------------------------------


class TestClose:
    """close() sends sentinel to terminate subscribers."""

    async def test_close_scope_terminates_subscriber(self) -> None:
        bus = ReactiveBus()
        exited = asyncio.Event()

        async def collect() -> None:
            async for _event in bus.subscribe("s"):
                pass  # pragma: no cover
            exited.set()

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)
        bus.close("s")
        await asyncio.wait_for(exited.wait(), timeout=1.0)
        await task
        assert exited.is_set()

    async def test_close_all_terminates_all_subscribers(self) -> None:
        bus = ReactiveBus()
        exited_a = asyncio.Event()
        exited_b = asyncio.Event()

        async def collect(scope: str, flag: asyncio.Event) -> None:
            async for _event in bus.subscribe(scope):
                pass  # pragma: no cover
            flag.set()

        task_a = asyncio.create_task(collect("a", exited_a))
        task_b = asyncio.create_task(collect("b", exited_b))
        await asyncio.sleep(0.01)
        bus.close()  # close all
        await asyncio.wait_for(
            asyncio.gather(exited_a.wait(), exited_b.wait()), timeout=1.0
        )
        await asyncio.gather(task_a, task_b)
        assert exited_a.is_set()
        assert exited_b.is_set()

    async def test_close_nonexistent_scope_is_noop(self) -> None:
        bus = ReactiveBus()
        bus.close("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# Back-pressure
# ---------------------------------------------------------------------------


class TestBackPressure:
    """When a subscriber's queue is full, events are silently dropped."""

    async def test_full_queue_drops_event(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for ev in bus.subscribe("s"):
                received.append(ev)  # noqa: PERF401

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)

        # Queue maxsize is 256 — fill it up and then some.
        # emit_sync uses put_nowait so it never blocks.
        for i in range(300):
            bus.emit_sync(_event("s", f"p.{i}"))

        # Let the collector drain, then close
        await asyncio.sleep(0.05)
        bus.close("s")
        await task

        # Should have exactly 256 (queue capacity) — excess dropped
        assert len(received) == 256


# ---------------------------------------------------------------------------
# Cleanup on subscriber exit
# ---------------------------------------------------------------------------


class TestCleanup:
    """Subscriber exit removes its queue from internal state."""

    async def test_subscriber_exit_cleans_up(self) -> None:
        bus = ReactiveBus()

        async def collect() -> None:
            async for _ev in bus.subscribe("s"):
                break  # exit after first event

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)
        assert len(bus._subscribers.get("s", set())) == 1
        await bus.emit(_event("s"))
        await task
        # Allow the finally block to run
        await asyncio.sleep(0.01)
        # After exit, the scope should be cleaned up
        assert "s" not in bus._subscribers or len(bus._subscribers["s"]) == 0


# ---------------------------------------------------------------------------
# Empty scope (no subscribers)
# ---------------------------------------------------------------------------


class TestEmptyScope:
    """Emitting to a scope with no subscribers is a no-op."""

    async def test_emit_no_subscribers(self) -> None:
        bus = ReactiveBus()
        # Should not raise
        await bus.emit(_event("nobody-listening"))
        bus.emit_sync(_event("nobody-listening"))


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """emit_sync called from a background thread reaches async subscribers."""

    async def test_emit_from_thread(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for event in bus.subscribe("s"):
                received.append(event)
                break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)

        # Emit from a separate thread
        def background() -> None:
            bus.emit_sync(_event("s", "from-thread"))

        thread = threading.Thread(target=background)
        thread.start()
        thread.join()

        await task
        assert len(received) == 1
        assert received[0].changed_paths == frozenset({"from-thread"})

    async def test_concurrent_emit_from_multiple_threads(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []
        count = 50

        async def collect() -> None:
            async for event in bus.subscribe("s"):
                received.append(event)
                if len(received) >= count:
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.01)

        barrier = threading.Barrier(count)

        def background(n: int) -> None:
            barrier.wait()
            bus.emit_sync(_event("s", f"thread-{n}"))

        threads = [threading.Thread(target=background, args=(i,)) for i in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        await asyncio.wait_for(task, timeout=2.0)
        assert len(received) == count
