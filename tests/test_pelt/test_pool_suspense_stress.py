"""Suspense-shaped concurrent Pelt pool checkout stress (#957).

Models Chirp Suspense defer fan-out: each "page" resolves many independent
deferred keys concurrently (``anyio`` task group), and each key checks out a
pooled connection, mutates connection-local state, then returns it. Overlapping
pages interleave acquire/release the way deferred DB work does under load.

This is a deterministic CI correctness gate — exclusive ownership, no
double-release, pool returns to idle — not a throughput benchmark.

Pool sizing relative to defer fan-out
-------------------------------------
Size the Pelt pool at least as large as the maximum number of deferred keys
that may hold a connection at once (the Suspense defer fan-out for a page, or
the overlapping fan-out across concurrent requests). Undersizing is safe
(checkouts queue on the pool semaphore) but stalls shell→OOB progress until a
connection frees. Full guidance for Pelt pool size versus Pounce worker count
belongs in #958; this stress only proves the checkout contract under fan-out
pressure.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest

from chirp.data.drivers._pelt import _runtime
from chirp.data.drivers._pelt.pool import Pool

# Suspense page: DEFER_FANOUT independent deferred keys resolve together.
# Pool is intentionally smaller so checkouts queue — the common undersized case.
POOL_SIZE = 4
DEFER_FANOUT = 8
PAGE_COUNT = 48
# Extra overlapping waves so acquire/release from different "pages" interleave.
OVERLAP_WAVES = 3


class _OwnedConnection:
    """Pool probe with connection-local mutable state (exclusive-owner contract)."""

    def __init__(self, identifier: int) -> None:
        self.identifier = identifier
        self.owner_token: int | None = None
        self.pad: list[int] = []
        self.reset_count = 0
        self.close_count = 0

    async def reset_if_needed(self) -> None:
        # Yield like a real reset round-trip so releases interleave with acquires.
        await anyio.sleep(0)
        self.reset_count += 1

    async def close(self) -> None:
        self.close_count += 1


def _assert_idle(pool: Pool, connections: list[_OwnedConnection]) -> None:
    assert len(pool._available) == pool.size == len(connections)
    assert set(pool._available) == set(pool._all) == set(connections)
    assert all(conn.owner_token is None for conn in connections)
    # No duplicate entries after a burst (would indicate double-release).
    assert len(pool._available) == len({id(c) for c in pool._available})


@pytest.mark.issue(957)
async def test_suspense_shaped_pool_checkout_stress_stays_exclusive_and_idle() -> None:
    """Many overlapping Suspense-like defer fan-outs: exclusive checkout, idle pool."""
    connections = [_OwnedConnection(index) for index in range(POOL_SIZE)]
    pool = Pool(cast(Any, connections))

    active: set[int] = set()
    active_lock = anyio.Lock()
    token_counter = 0
    token_lock = anyio.Lock()
    acquire_count = 0
    release_count = 0
    counts_lock = anyio.Lock()
    # Tracks connections currently sitting in `_available` to catch double-release.
    available_ids = {id(c) for c in connections}

    async def defer_key(page_id: int, key_index: int) -> None:
        nonlocal token_counter, acquire_count, release_count
        conn = cast(_OwnedConnection, await pool.acquire())
        async with counts_lock:
            acquire_count += 1
            available_ids.discard(id(conn))

        async with token_lock:
            token_counter += 1
            token = token_counter

        async with active_lock:
            assert conn.identifier not in active, (
                f"cross-checkout: connection {conn.identifier} already active "
                f"(page={page_id} key={key_index})"
            )
            active.add(conn.identifier)
            assert conn.owner_token is None
            conn.owner_token = token

        # Connection-local mutation while exclusively owned (codec ledger analogue).
        conn.pad.append(token)
        await anyio.sleep(0)
        assert conn.owner_token == token
        assert conn.pad[-1] == token

        async with active_lock:
            active.remove(conn.identifier)
            conn.owner_token = None

        async with counts_lock:
            # Double-release would put the same connection back twice.
            assert id(conn) not in available_ids, (
                f"double-release: connection {conn.identifier} already idle "
                f"(page={page_id} key={key_index})"
            )
            available_ids.add(id(conn))
            release_count += 1

        await pool.release(cast(Any, conn))

    async def suspense_page(page_id: int) -> None:
        async with anyio.create_task_group() as tg:
            for key_index in range(DEFER_FANOUT):
                tg.start_soon(defer_key, page_id, key_index)

    # Overlapping waves: start several pages before earlier ones finish.
    async with anyio.create_task_group() as outer:
        for wave in range(OVERLAP_WAVES):
            for page in range(PAGE_COUNT // OVERLAP_WAVES):
                page_id = wave * (PAGE_COUNT // OVERLAP_WAVES) + page
                outer.start_soon(suspense_page, page_id)
            # Yield so later waves stack on in-flight checkouts.
            await anyio.sleep(0)

    expected = PAGE_COUNT * DEFER_FANOUT
    assert acquire_count == release_count == expected
    assert active == set()
    assert sum(conn.reset_count for conn in connections) == expected
    _assert_idle(pool, connections)
    await pool.close()
    assert all(conn.close_count == 1 for conn in connections)


@pytest.mark.issue(957)
async def test_suspense_shaped_pool_survives_undersized_fanout_burst() -> None:
    """Fan-out larger than pool size queues safely and still returns to idle.

    Documents the sizing rule: prefer ``pool_size >= defer_fan_out`` (and see
    #958 for Pounce worker count). Undersizing must not corrupt ownership.
    """
    connections = [_OwnedConnection(index) for index in range(2)]
    pool = Pool(cast(Any, connections))
    max_inflight = 0
    inflight = 0
    inflight_lock = anyio.Lock()

    async def defer_key() -> None:
        nonlocal max_inflight, inflight
        conn = cast(_OwnedConnection, await pool.acquire())
        async with inflight_lock:
            inflight += 1
            max_inflight = max(max_inflight, inflight)
            assert inflight <= pool.size
        conn.pad.append(1)
        await anyio.sleep(0)
        async with inflight_lock:
            inflight -= 1
        await pool.release(cast(Any, conn))

    async with anyio.create_task_group() as tg:
        for _ in range(24):
            tg.start_soon(defer_key)

    assert max_inflight == pool.size == 2
    assert inflight == 0
    _assert_idle(pool, connections)
    await pool.close()


@pytest.mark.issue(957)
@pytest.mark.skipif(
    not _runtime.is_free_threading_enabled(),
    reason="requires a free-threaded build with GIL disabled",
)
def test_suspense_shaped_pool_checkout_stress_from_native_threads() -> None:
    """Thread shape: each native thread drives one Suspense-like page via anyio.

    Pool instances are not shared across event loops; each thread owns its pool.
    This proves the Suspense fan-out stress remains green under free-threading
    (many native threads, each running overlapping defer checkouts), complementary
    to the single-loop async stress above.
    """
    from tests.test_concurrency.conftest import assert_no_errors, run_threads_synchronized

    thread_count = 4
    pages_per_thread = 8
    fan_out = 6
    pool_size = 3

    def worker(index: int, barrier: threading.Barrier, result: Any) -> None:
        barrier.wait()

        async def run_pages() -> SimpleNamespace:
            connections = [_OwnedConnection(i) for i in range(pool_size)]
            pool = Pool(cast(Any, connections))
            active: set[int] = set()
            active_lock = anyio.Lock()

            async def defer_key(token: int) -> None:
                conn = cast(_OwnedConnection, await pool.acquire())
                async with active_lock:
                    assert conn.identifier not in active
                    active.add(conn.identifier)
                    assert conn.owner_token is None
                    conn.owner_token = token
                conn.pad.append(token)
                await anyio.sleep(0)
                assert conn.owner_token == token
                async with active_lock:
                    active.remove(conn.identifier)
                    conn.owner_token = None
                await pool.release(cast(Any, conn))

            async def page(page_id: int) -> None:
                async with anyio.create_task_group() as tg:
                    for key in range(fan_out):
                        tg.start_soon(defer_key, page_id * fan_out + key)

            async with anyio.create_task_group() as tg:
                for page_id in range(pages_per_thread):
                    tg.start_soon(page, page_id)

            assert active == set()
            _assert_idle(pool, connections)
            await pool.close()
            return SimpleNamespace(
                thread=index,
                resets=sum(c.reset_count for c in connections),
                expected=pages_per_thread * fan_out,
            )

        outcome = anyio.run(run_pages)
        assert outcome.resets == outcome.expected
        result.record(outcome)

    stress = run_threads_synchronized(thread_count, worker)
    assert_no_errors(stress)
    assert len(stress.results) == thread_count
