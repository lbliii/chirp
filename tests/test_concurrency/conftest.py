"""Reusable synchronization primitives for deterministic concurrency tests.

Design Principles
-----------------
1. **Barrier-based start**: All threads/tasks begin work simultaneously
   via ``threading.Barrier`` (threads) or ``asyncio.Event`` (tasks).
2. **Bounded waits**: Every blocking call has an explicit timeout to
   prevent hangs.  Default: 5 seconds.
3. **At-least-N assertions**: Concurrency means exact counts are
   sometimes non-deterministic.  Use ``assert_at_least`` for soft
   lower bounds and exact assertions only when the design guarantees
   delivery.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# Default timeout for all bounded waits in stress tests.
STRESS_TIMEOUT: float = 5.0


# ---------------------------------------------------------------------------
# Thread helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ThreadStressResult:
    """Collects results from a batch of stress threads."""

    results: list[Any] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, value: Any) -> None:
        with self._lock:
            self.results.append(value)

    def record_error(self, exc: Exception) -> None:
        with self._lock:
            self.errors.append(exc)


def run_threads_synchronized(
    count: int,
    target: Callable[[int, threading.Barrier, ThreadStressResult], None],
    *,
    timeout: float = STRESS_TIMEOUT,
) -> ThreadStressResult:
    """Launch *count* threads that start simultaneously via a Barrier.

    Each thread calls ``target(thread_index, barrier, result)``.
    The barrier ensures all threads begin work at the same instant,
    maximizing contention.

    Returns a ``ThreadStressResult`` with all collected values and errors.
    Raises ``TimeoutError`` if any thread doesn't finish within *timeout*.
    """
    barrier = threading.Barrier(count)
    result = ThreadStressResult()

    threads = [
        threading.Thread(target=target, args=(i, barrier, result), daemon=True)
        for i in range(count)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
        if t.is_alive():
            raise TimeoutError(f"Thread did not finish within {timeout}s")

    return result


# ---------------------------------------------------------------------------
# Async task helpers
# ---------------------------------------------------------------------------


async def run_tasks_synchronized(
    count: int,
    coro_factory: Callable[[int, asyncio.Event], Awaitable[Any]],
    *,
    timeout: float = STRESS_TIMEOUT,
) -> list[Any]:
    """Launch *count* async tasks that start simultaneously via an Event.

    Each task calls ``await coro_factory(task_index, start_event)`` and
    should ``await start_event.wait()`` before doing real work.

    Returns a list of return values from each task.
    Raises ``TimeoutError`` if the gather doesn't complete within *timeout*.
    """
    start = asyncio.Event()
    tasks = [asyncio.create_task(coro_factory(i, start)) for i in range(count)]

    # Let all tasks reach their wait point
    await asyncio.sleep(0.01)
    start.set()

    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=timeout)
    return list(results)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def assert_at_least(actual: int, minimum: int, label: str = "count") -> None:
    """Assert that *actual* >= *minimum* with a descriptive message.

    Use this for soft lower bounds where exact delivery isn't guaranteed
    (e.g., when back-pressure may drop some events).
    """
    assert actual >= minimum, f"Expected {label} >= {minimum}, got {actual}"


def assert_no_errors(result: ThreadStressResult) -> None:
    """Assert that no thread raised an exception."""
    if result.errors:
        msgs = [f"  {type(e).__name__}: {e}" for e in result.errors[:5]]
        tail = f"\n  ... and {len(result.errors) - 5} more" if len(result.errors) > 5 else ""
        raise AssertionError(
            f"{len(result.errors)} thread(s) raised errors:\n" + "\n".join(msgs) + tail
        )
