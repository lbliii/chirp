"""Tests for ReactiveBus observability counters and configurable queue size."""

import asyncio

import pytest

from chirp.pages.reactive import ChangeEvent, ReactiveBus

POLL_INTERVAL = 0.005
WAIT_TIMEOUT = 2.0


def _event(scope: str = "s", path: str = "x") -> ChangeEvent:
    return ChangeEvent(scope=scope, changed_paths=frozenset({path}))


async def _wait_for_subscribers(
    bus: ReactiveBus,
    expected: int,
    *,
    timeout: float = WAIT_TIMEOUT,
) -> None:
    """Poll subscriber_count until it reaches *expected*."""
    import time

    deadline = time.monotonic() + timeout
    while bus.subscriber_count < expected:
        if time.monotonic() > deadline:
            msg = f"Timed out waiting for {expected} subscribers (got {bus.subscriber_count})"
            raise TimeoutError(msg)
        await asyncio.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Observability counters
# ---------------------------------------------------------------------------


class TestEmittedCount:
    """emitted_count tracks total emissions."""

    async def test_starts_at_zero(self) -> None:
        bus = ReactiveBus()
        assert bus.emitted_count == 0

    async def test_increments_per_emit(self) -> None:
        bus = ReactiveBus()
        bus.emit_sync(_event())
        bus.emit_sync(_event())
        bus.emit_sync(_event())
        assert bus.emitted_count == 3

    async def test_counts_even_with_no_subscribers(self) -> None:
        bus = ReactiveBus()
        bus.emit_sync(_event("nobody"))
        assert bus.emitted_count == 1


class TestDroppedCount:
    """dropped_count tracks events lost to back-pressure."""

    async def test_starts_at_zero(self) -> None:
        bus = ReactiveBus()
        assert bus.dropped_count == 0

    async def test_counts_drops_on_full_queue(self) -> None:
        bus = ReactiveBus(maxsize=4)
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for ev in bus.subscribe("s"):
                received.append(ev)  # noqa: PERF401

        task = asyncio.create_task(collect())
        await _wait_for_subscribers(bus, 1)

        # Emit 10 events into a queue of size 4
        for i in range(10):
            bus.emit_sync(_event("s", f"p-{i}"))

        await asyncio.sleep(0.05)
        bus.close("s")
        await task

        assert len(received) == 4
        assert bus.dropped_count == 6
        assert bus.emitted_count == 10

    async def test_no_drops_when_queue_not_full(self) -> None:
        bus = ReactiveBus(maxsize=256)
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for ev in bus.subscribe("s"):
                received.append(ev)
                if len(received) >= 5:
                    break

        task = asyncio.create_task(collect())
        await _wait_for_subscribers(bus, 1)

        for i in range(5):
            bus.emit_sync(_event("s", f"p-{i}"))

        await task
        assert bus.dropped_count == 0


class TestSubscriberCount:
    """subscriber_count tracks active subscribers."""

    async def test_starts_at_zero(self) -> None:
        bus = ReactiveBus()
        assert bus.subscriber_count == 0

    async def test_increments_on_subscribe(self) -> None:
        bus = ReactiveBus()

        async def sub() -> None:
            async for _ev in bus.subscribe("s"):
                break

        task = asyncio.create_task(sub())
        await _wait_for_subscribers(bus, 1)
        assert bus.subscriber_count == 1

        bus.emit_sync(_event("s"))
        await task
        await asyncio.sleep(0.01)
        assert bus.subscriber_count == 0

    async def test_multiple_scopes(self) -> None:
        bus = ReactiveBus()

        async def sub(scope: str) -> None:
            async for _ev in bus.subscribe(scope):
                pass

        tasks = [asyncio.create_task(sub(f"scope-{i}")) for i in range(5)]
        await _wait_for_subscribers(bus, 5)
        assert bus.subscriber_count == 5

        bus.close()
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.01)
        assert bus.subscriber_count == 0


# ---------------------------------------------------------------------------
# Maxsize validation
# ---------------------------------------------------------------------------


class TestMaxsizeValidation:
    """ReactiveBus rejects invalid maxsize values."""

    def test_zero_maxsize_raises(self) -> None:
        with pytest.raises(ValueError, match="maxsize must be >= 1"):
            ReactiveBus(maxsize=0)

    def test_negative_maxsize_raises(self) -> None:
        with pytest.raises(ValueError, match="maxsize must be >= 1"):
            ReactiveBus(maxsize=-1)


# ---------------------------------------------------------------------------
# Configurable queue size
# ---------------------------------------------------------------------------


class TestConfigurableMaxsize:
    """ReactiveBus(maxsize=N) controls per-subscriber queue depth."""

    async def test_default_maxsize_is_256(self) -> None:
        bus = ReactiveBus()
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for ev in bus.subscribe("s"):
                received.append(ev)  # noqa: PERF401

        task = asyncio.create_task(collect())
        await _wait_for_subscribers(bus, 1)

        for i in range(300):
            bus.emit_sync(_event("s", f"p-{i}"))

        await asyncio.sleep(0.05)
        bus.close("s")
        await task
        assert len(received) == 256

    async def test_custom_maxsize_64(self) -> None:
        bus = ReactiveBus(maxsize=64)
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for ev in bus.subscribe("s"):
                received.append(ev)  # noqa: PERF401

        task = asyncio.create_task(collect())
        await _wait_for_subscribers(bus, 1)

        for i in range(100):
            bus.emit_sync(_event("s", f"p-{i}"))

        await asyncio.sleep(0.05)
        bus.close("s")
        await task
        assert len(received) == 64

    async def test_custom_maxsize_512(self) -> None:
        bus = ReactiveBus(maxsize=512)
        received: list[ChangeEvent] = []

        async def collect() -> None:
            async for ev in bus.subscribe("s"):
                received.append(ev)  # noqa: PERF401

        task = asyncio.create_task(collect())
        await _wait_for_subscribers(bus, 1)

        for i in range(600):
            bus.emit_sync(_event("s", f"p-{i}"))

        await asyncio.sleep(0.05)
        bus.close("s")
        await task
        assert len(received) == 512
