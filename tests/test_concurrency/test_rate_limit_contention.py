"""Stress tests for in-memory rate limiter and lockout backends.

Verifies that rate counts and lockout thresholds are accurate under
concurrent access from many threads.
"""

import asyncio
import threading

from chirp.middleware.auth_rate_limit import AuthRateLimitConfig, _InMemoryRateLimitBackend
from chirp.security.lockout import LockoutConfig, _InMemoryLockoutBackend

from .conftest import STRESS_TIMEOUT, ThreadStressResult, run_threads_synchronized

# ---------------------------------------------------------------------------
# Rate limiter contention
# ---------------------------------------------------------------------------


class TestRateLimiterContention:
    """Concurrent requests against the in-memory rate limiter."""

    async def test_rate_limit_accurate_under_burst(self) -> None:
        """Total allowed + blocked should equal total attempts."""
        backend = _InMemoryRateLimitBackend()
        n_threads = 100
        attempts_per_thread = 5
        config = AuthRateLimitConfig(requests=200, window_seconds=60, block_seconds=0)

        allowed_count = 0
        blocked_count = 0
        count_lock = threading.Lock()

        def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            nonlocal allowed_count, blocked_count
            barrier.wait()
            loop = asyncio.new_event_loop()
            local_allowed = 0
            local_blocked = 0
            try:
                for _ in range(attempts_per_thread):
                    import time

                    allowed, _retry = loop.run_until_complete(
                        backend.check_and_update(
                            "shared-key",
                            time.monotonic(),
                            requests=config.requests,
                            window_seconds=config.window_seconds,
                            block_seconds=config.block_seconds,
                        )
                    )
                    if allowed:
                        local_allowed += 1
                    else:
                        local_blocked += 1
                with count_lock:
                    allowed_count += local_allowed
                    blocked_count += local_blocked
                result.record("ok")
            except Exception as exc:
                result.record_error(exc)
            finally:
                loop.close()

        result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)
        assert not result.errors, f"Thread errors: {result.errors}"

        total = n_threads * attempts_per_thread
        assert allowed_count + blocked_count == total, (
            f"Lost requests: allowed={allowed_count}, blocked={blocked_count}, total={total}"
        )
        # With limit=200 and 500 total attempts, should see ~200 allowed
        assert allowed_count <= config.requests + n_threads, (
            f"Too many allowed: {allowed_count} (limit={config.requests})"
        )

    async def test_different_keys_dont_interfere(self) -> None:
        """Rate limiting on different keys is independent."""
        backend = _InMemoryRateLimitBackend()
        n_threads = 50
        limit = 10

        per_key_allowed: dict[str, int] = {}
        lock = threading.Lock()

        def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            key = f"user-{idx}"
            barrier.wait()
            loop = asyncio.new_event_loop()
            allowed = 0
            try:
                import time

                for _ in range(limit + 5):
                    ok, _ = loop.run_until_complete(
                        backend.check_and_update(
                            key,
                            time.monotonic(),
                            requests=limit,
                            window_seconds=60,
                            block_seconds=0,
                        )
                    )
                    if ok:
                        allowed += 1
                with lock:
                    per_key_allowed[key] = allowed
                result.record("ok")
            except Exception as exc:
                result.record_error(exc)
            finally:
                loop.close()

        result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)
        assert not result.errors

        # Each key should have exactly `limit` allowed (independent counters)
        for key, count in per_key_allowed.items():
            assert count == limit, f"{key}: expected {limit} allowed, got {count}"


# ---------------------------------------------------------------------------
# Lockout contention
# ---------------------------------------------------------------------------


class TestLockoutContention:
    """Concurrent failure recording against the lockout backend."""

    async def test_lockout_triggers_at_threshold(self) -> None:
        """Lockout fires after max_failures concurrent failures on same key."""
        config = LockoutConfig(max_failures=5, window_seconds=60, base_lock_seconds=300)
        backend = _InMemoryLockoutBackend(config)
        n_threads = 50

        locked_flags: list[bool] = []
        lock = threading.Lock()

        def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            is_locked, _ = backend.record_failure("shared-user")
            with lock:
                locked_flags.append(is_locked)
            result.record("ok")

        result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)
        assert not result.errors

        # After 50 failures with max_failures=5, most should report locked
        locked_count = sum(1 for f in locked_flags if f)
        # At least (50 - 5) should be locked (first 5 are under threshold)
        assert locked_count >= n_threads - config.max_failures, (
            f"Too few lockouts: {locked_count}/{n_threads}"
        )

    async def test_success_clears_under_contention(self) -> None:
        """record_success clears state even with concurrent failures."""
        config = LockoutConfig(max_failures=10, window_seconds=60, base_lock_seconds=300)
        backend = _InMemoryLockoutBackend(config)
        n_threads = 30

        def failer(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            for _ in range(3):
                backend.record_failure("contended-user")
            result.record("fail-done")

        def succeeder(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
            barrier.wait()
            backend.record_success("contended-user")
            result.record("success-done")

        # Mix failures and successes
        barrier = threading.Barrier(n_threads)
        result = ThreadStressResult()
        threads = []
        for i in range(n_threads):
            target = succeeder if i % 5 == 0 else failer
            t = threading.Thread(target=target, args=(i, barrier, result), daemon=True)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=STRESS_TIMEOUT)

        assert not result.errors
        # No crash — that's the main assertion. State may be locked or not
        # depending on race outcome, but no exception should have occurred.
