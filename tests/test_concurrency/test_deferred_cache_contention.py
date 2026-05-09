"""Contention tests for DeferredCache in-flight coordination."""

import asyncio
import inspect
import threading

from chirp.cache import DeferredCache

from .conftest import ThreadStressResult, run_threads_synchronized


def test_deferred_cache_concurrent_same_key_miss_runs_factory_once() -> None:
    cache = DeferredCache(default_ttl=60)
    calls = 0
    calls_lock = threading.Lock()

    async def factory() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        await asyncio.sleep(0.02)
        return "shared"

    def worker(_idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
        try:
            barrier.wait(timeout=5)
            value_or_awaitable = cache.get_or_defer("hot-key", factory)
            if inspect.isawaitable(value_or_awaitable):
                value = asyncio.run(value_or_awaitable)
            else:
                value = value_or_awaitable
            if value != "shared":
                result.record_error(AssertionError(f"expected shared, got {value!r}"))
                return
            result.record(value)
        except Exception as exc:
            result.record_error(exc)

    result = run_threads_synchronized(12, worker)

    assert not result.errors
    assert result.results == ["shared"] * 12
    assert calls == 1
    assert cache.get_or_defer("hot-key", factory) == "shared"
