"""Stress tests for MemoryCacheBackend under concurrent thread access.

Verifies that get/set/delete operations are safe under contention
from 100+ threads operating on overlapping keys.
"""

import asyncio
import threading

from chirp.cache.backends.memory import MemoryCacheBackend

from .conftest import STRESS_TIMEOUT, ThreadStressResult, run_threads_synchronized


class TestCacheContention:
    """100 threads doing concurrent get/set/delete on overlapping keys."""

    async def test_concurrent_set_get_no_corruption(self) -> None:
        """Values are never corrupted — get returns either the set value or None."""
        cache = MemoryCacheBackend()
        n_threads = 100
        ops_per_thread = 50

        errors: list[str] = []
        lock = threading.Lock()

        def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            loop = asyncio.new_event_loop()
            try:
                for i in range(ops_per_thread):
                    key = f"key-{i % 10}"  # 10 shared keys
                    value = f"val-{idx}-{i}".encode()

                    loop.run_until_complete(cache.set(key, value))
                    got = loop.run_until_complete(cache.get(key))

                    # Got must be a valid value (from any thread) or None
                    if got is not None and not got.startswith(b"val-"):
                        with lock:
                            errors.append(f"Corrupt value: {got!r}")

                result.record(ops_per_thread)
            except Exception as exc:
                result.record_error(exc)
            finally:
                loop.close()

        result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)

        assert not errors, f"Corruption detected: {errors}"
        assert not result.errors, f"Thread errors: {result.errors}"
        assert len(result.results) == n_threads

    async def test_concurrent_delete_no_keyerror(self) -> None:
        """Concurrent deletes on same key never raise KeyError."""
        cache = MemoryCacheBackend()
        n_threads = 50

        def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            loop = asyncio.new_event_loop()
            try:
                for i in range(100):
                    key = f"shared-{i % 5}"
                    loop.run_until_complete(cache.set(key, b"data"))
                    loop.run_until_complete(cache.delete(key))
                    loop.run_until_complete(cache.delete(key))  # double delete
                result.record("ok")
            except Exception as exc:
                result.record_error(exc)
            finally:
                loop.close()

        result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)
        assert not result.errors, f"Thread errors: {result.errors}"

    async def test_concurrent_clear_with_operations(self) -> None:
        """clear() during set/get doesn't corrupt state."""
        cache = MemoryCacheBackend()
        n_threads = 50

        def writer(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            loop = asyncio.new_event_loop()
            try:
                for i in range(100):
                    loop.run_until_complete(cache.set(f"k-{idx}-{i}", b"v"))
                result.record("ok")
            except Exception as exc:
                result.record_error(exc)
            finally:
                loop.close()

        def clearer(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            loop = asyncio.new_event_loop()
            try:
                for _ in range(20):
                    loop.run_until_complete(cache.clear())
                result.record("ok")
            except Exception as exc:
                result.record_error(exc)
            finally:
                loop.close()

        # Mix writers and clearers
        barrier = threading.Barrier(n_threads)
        result = ThreadStressResult()
        threads = []
        for i in range(n_threads):
            target = clearer if i % 10 == 0 else writer
            t = threading.Thread(target=target, args=(i, barrier, result), daemon=True)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=STRESS_TIMEOUT)

        assert not result.errors, f"Thread errors: {result.errors}"

    async def test_ttl_expiry_under_contention(self) -> None:
        """TTL expiry is consistent even under concurrent access."""
        cache = MemoryCacheBackend()
        n_threads = 30

        def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            loop = asyncio.new_event_loop()
            try:
                key = "ttl-shared"
                # Set with very short TTL
                loop.run_until_complete(cache.set(key, b"ephemeral", ttl=1))
                # Get immediately — should be there
                got = loop.run_until_complete(cache.get(key))
                result.record("hit" if got is not None else "miss")
            except Exception as exc:
                result.record_error(exc)
            finally:
                loop.close()

        result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)
        assert not result.errors
        # Most threads should get a hit (TTL=1s, ops are fast)
        hits = sum(1 for r in result.results if r == "hit")
        assert hits >= n_threads // 2, f"Too few hits: {hits}/{n_threads}"
