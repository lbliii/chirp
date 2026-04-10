"""Stress tests for ReactiveBus under high concurrency.

Covers scenarios beyond the basic functional tests in test_reactive_bus.py:
- Many subscribers + many emitters simultaneously
- Queue saturation with multiple fast emitters
- close() racing with emit_sync()
- subscribe() racing with close()
"""

import asyncio
import threading

from chirp.pages.reactive import ChangeEvent, ReactiveBus

from .conftest import STRESS_TIMEOUT, assert_at_least


def _event(scope: str = "s", path: str = "x") -> ChangeEvent:
    return ChangeEvent(scope=scope, changed_paths=frozenset({path}))


# ---------------------------------------------------------------------------
# Many subscribers + many emitters
# ---------------------------------------------------------------------------


class TestManySubscribersManyEmitters:
    """100 subscribers, 50 emitter threads, all on the same scope."""

    async def test_all_subscribers_receive_at_least_one_event(self) -> None:
        bus = ReactiveBus()
        n_subscribers = 100
        n_emitters = 50
        received: list[list[ChangeEvent]] = [[] for _ in range(n_subscribers)]

        async def collect(idx: int) -> None:
            async for event in bus.subscribe("s"):
                received[idx].append(event)
                if len(received[idx]) >= 1:
                    break

        tasks = [asyncio.create_task(collect(i)) for i in range(n_subscribers)]
        await asyncio.sleep(0.05)

        barrier = threading.Barrier(n_emitters)

        def emit_thread(n: int) -> None:
            barrier.wait()
            bus.emit_sync(_event("s", f"emitter-{n}"))

        threads = [threading.Thread(target=emit_thread, args=(i,)) for i in range(n_emitters)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=STRESS_TIMEOUT)

        # All tasks should complete (each got at least 1 event)
        _done, pending = await asyncio.wait(tasks, timeout=STRESS_TIMEOUT)
        # Clean up any stragglers
        bus.close("s")
        if pending:
            await asyncio.wait(pending, timeout=1.0)

        subscribers_that_received = sum(1 for r in received if len(r) >= 1)
        assert_at_least(subscribers_that_received, n_subscribers, "subscribers with events")

    async def test_no_deadlock_under_contention(self) -> None:
        """Verify the bus doesn't deadlock with many concurrent operations."""
        bus = ReactiveBus()
        n_emitters = 100

        async def subscriber() -> int:
            count = 0
            async for _event in bus.subscribe("s"):
                count += 1
                if count >= 50:
                    break
            return count

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.02)

        barrier = threading.Barrier(n_emitters)

        def emit_thread(n: int) -> None:
            barrier.wait()
            for _ in range(5):
                bus.emit_sync(_event("s", f"t-{n}"))

        threads = [threading.Thread(target=emit_thread, args=(i,)) for i in range(n_emitters)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=STRESS_TIMEOUT)

        result = await asyncio.wait_for(task, timeout=STRESS_TIMEOUT)
        assert_at_least(result, 50, "events received")


# ---------------------------------------------------------------------------
# Queue saturation with multiple fast emitters
# ---------------------------------------------------------------------------


class TestQueueSaturation:
    """Multiple emitters overwhelm a single subscriber's queue."""

    async def test_multiple_emitters_saturate_queue(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for event in bus.subscribe("s"):
                received.append(event)  # noqa: PERF401

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.02)

        n_emitters = 20
        events_per_emitter = 50  # 20 * 50 = 1000, well above queue maxsize=256
        barrier = threading.Barrier(n_emitters)

        def flood(n: int) -> None:
            barrier.wait()
            for i in range(events_per_emitter):
                bus.emit_sync(_event("s", f"flood-{n}-{i}"))

        threads = [threading.Thread(target=flood, args=(i,)) for i in range(n_emitters)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=STRESS_TIMEOUT)

        await asyncio.sleep(0.1)
        bus.close("s")
        await asyncio.wait_for(task, timeout=STRESS_TIMEOUT)

        # Queue maxsize is 256 — should receive at most 256 before
        # the subscriber drains. With async draining, may get more
        # (drain + refill cycles). But should never exceed total emitted.
        total_emitted = n_emitters * events_per_emitter
        assert len(received) <= total_emitted
        # Should have received a meaningful number (at least queue capacity)
        assert_at_least(len(received), 256, "events received under saturation")


# ---------------------------------------------------------------------------
# close() racing with emit_sync()
# ---------------------------------------------------------------------------


class TestCloseRaceEmit:
    """close() and emit_sync() called concurrently — no crash, no hang."""

    async def test_close_during_emit_no_exception(self) -> None:
        bus = ReactiveBus()
        errors: list[Exception] = []

        async def subscriber() -> None:
            async for _event in bus.subscribe("s"):
                pass

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.02)

        barrier = threading.Barrier(2)

        def emit_loop() -> None:
            barrier.wait()
            for i in range(500):
                try:
                    bus.emit_sync(_event("s", f"race-{i}"))
                except Exception as exc:
                    errors.append(exc)

        def close_thread() -> None:
            barrier.wait()
            try:
                bus.close("s")
            except Exception as exc:
                errors.append(exc)

        t_emit = threading.Thread(target=emit_loop)
        t_close = threading.Thread(target=close_thread)
        t_emit.start()
        t_close.start()
        t_emit.join(timeout=STRESS_TIMEOUT)
        t_close.join(timeout=STRESS_TIMEOUT)

        # Subscriber should have exited (via sentinel from close)
        await asyncio.wait_for(task, timeout=STRESS_TIMEOUT)
        assert not errors, f"Exceptions during race: {errors}"


# ---------------------------------------------------------------------------
# subscribe() racing with close()
# ---------------------------------------------------------------------------


class TestSubscribeRaceClose:
    """subscribe() and close() called concurrently — clean termination."""

    async def test_subscribe_during_close_terminates_cleanly(self) -> None:
        bus = ReactiveBus()
        results: list[str] = []

        async def late_subscriber() -> None:
            """Subscribe after a brief delay — may arrive before or after close."""
            await asyncio.sleep(0.01)
            count = 0
            async for _event in bus.subscribe("s"):
                count += 1
            results.append(f"collected-{count}")

        task = asyncio.create_task(late_subscriber())

        # Give subscriber time to register, then close from another thread
        await asyncio.sleep(0.03)

        def close_thread() -> None:
            bus.close("s")

        t = threading.Thread(target=close_thread)
        t.start()
        t.join(timeout=STRESS_TIMEOUT)

        await asyncio.wait_for(task, timeout=STRESS_TIMEOUT)
        # Subscriber should have exited cleanly (0 events)
        assert len(results) == 1
        assert results[0] == "collected-0"


# ---------------------------------------------------------------------------
# Multi-scope stress
# ---------------------------------------------------------------------------


class TestMultiScopeStress:
    """Many scopes active simultaneously with concurrent emit + close."""

    async def test_many_scopes_no_cross_contamination(self) -> None:
        bus = ReactiveBus()
        n_scopes = 20
        received: dict[str, list[str]] = {f"scope-{i}": [] for i in range(n_scopes)}

        async def collect(scope: str) -> None:
            async for event in bus.subscribe(scope):
                received[scope].append(event.scope)
                if len(received[scope]) >= 3:
                    break

        tasks = [asyncio.create_task(collect(f"scope-{i}")) for i in range(n_scopes)]
        await asyncio.sleep(0.03)

        barrier = threading.Barrier(n_scopes)

        def emit_to_scope(idx: int) -> None:
            scope = f"scope-{idx}"
            barrier.wait()
            for _ in range(3):
                bus.emit_sync(ChangeEvent(scope=scope, changed_paths=frozenset({"p"})))

        threads = [threading.Thread(target=emit_to_scope, args=(i,)) for i in range(n_scopes)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=STRESS_TIMEOUT)

        await asyncio.wait_for(asyncio.gather(*tasks), timeout=STRESS_TIMEOUT)

        # Each scope should only have events from its own scope
        for scope, events in received.items():
            assert all(e == scope for e in events), f"{scope} received cross-scope events: {events}"
