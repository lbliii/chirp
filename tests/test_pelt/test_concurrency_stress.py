"""E6 (#259) — free-threading hardening and concurrency proof for pelt."""

from __future__ import annotations

import threading
import time
from types import MappingProxyType
from typing import Any, cast

import anyio
import pytest

from chirp.data.drivers._pelt import _codecs, _runtime
from chirp.data.drivers._pelt._codecs import OID_INT4, build_default_registry
from chirp.data.drivers._pelt._messages import FieldDescription, RowDescription
from chirp.data.drivers._pelt.connection import _decode_rows
from chirp.data.drivers._pelt.pool import Pool
from tests.test_concurrency.conftest import assert_no_errors, run_threads_synchronized


class _YieldingConnection:
    """Small pool probe whose reset deliberately yields to the scheduler."""

    def __init__(self, identifier: int) -> None:
        self.identifier = identifier
        self.reset_count = 0

    async def reset_if_needed(self) -> None:
        await anyio.sleep(0)
        self.reset_count += 1

    async def close(self) -> None:
        return None


class _BlockingResetConnection(_YieldingConnection):
    """Makes the reset/republication ordering directly observable."""

    def __init__(self) -> None:
        super().__init__(0)
        self.reset_started = anyio.Event()
        self.allow_reset = anyio.Event()
        self.reset_finished = False

    async def reset_if_needed(self) -> None:
        self.reset_started.set()
        await self.allow_reset.wait()
        self.reset_finished = True
        self.reset_count += 1


@pytest.mark.issue(259)
def test_should_parallelize_requires_threshold_and_nogil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_runtime, "is_free_threading_enabled", lambda: True)
    assert _runtime.should_parallelize(n_rows=64, n_cols=4) is True
    assert _runtime.should_parallelize(n_rows=63, n_cols=4) is False
    assert _runtime.should_parallelize(n_rows=64, n_cols=3) is False


@pytest.mark.issue(259)
def test_parallel_row_decode_matches_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = build_default_registry().snapshot()
    description = RowDescription(
        fields=(
            FieldDescription(
                name="n",
                table_oid=0,
                column_attr=0,
                type_oid=OID_INT4,
                type_size=4,
                type_modifier=-1,
                format_code=1,
            ),
        )
    )
    plan = _codecs.build_codec_plan(description, registry)
    pending = [(value.to_bytes(4, "big", signed=True),) for value in range(128)]
    monkeypatch.setattr(_runtime, "should_parallelize", lambda *, n_rows, n_cols: False)
    serial = _decode_rows(plan, ("n",), list(pending))
    monkeypatch.setattr(_runtime, "should_parallelize", lambda *, n_rows, n_cols: True)
    parallel = _decode_rows(plan, ("n",), list(pending))
    assert [dict(row) for row in serial] == [{"n": i} for i in range(128)]
    assert [dict(row) for row in parallel] == [{"n": i} for i in range(128)]


@pytest.mark.issue(259)
@pytest.mark.skipif(
    not _runtime.is_free_threading_enabled(),
    reason="requires a free-threaded build with GIL disabled",
)
def test_parallel_row_decode_overlaps_on_native_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate executor overlap; this is a correctness receipt, not a throughput benchmark."""
    per_decode = 0.04
    n_rows = 16
    thread_ids: set[int] = set()
    thread_ids_lock = threading.Lock()

    def decode(data: bytes) -> int:
        with thread_ids_lock:
            thread_ids.add(threading.get_native_id())
        time.sleep(per_decode)
        return int.from_bytes(data, "big", signed=True)

    monkeypatch.setattr(_runtime, "should_parallelize", lambda *, n_rows, n_cols: True)
    pending = [(value.to_bytes(4, "big", signed=True),) for value in range(n_rows)]

    started = time.perf_counter()
    rows = _decode_rows((decode,), ("n",), pending)
    elapsed = time.perf_counter() - started

    assert [dict(row) for row in rows] == [{"n": i} for i in range(n_rows)]
    assert len(thread_ids) >= 2
    assert elapsed < n_rows * per_decode / 2


@pytest.mark.issue(259)
def test_codec_registry_concurrent_writes_publish_untorn_snapshots() -> None:
    registry = _codecs.CodecRegistry()
    writer_finished = threading.Event()
    base_oid = 800_000
    codec_count = 64

    def worker(index: int, barrier: threading.Barrier, result) -> None:
        barrier.wait()
        if index == 0:
            for offset in range(codec_count):
                oid = base_oid + offset
                registry.register(_codecs._int_codec(oid, f"stress_int_{offset}", 4))
                if offset % 4 == 0:
                    time.sleep(0)
            writer_finished.set()
            result.record(("writer", codec_count))
            return

        sizes: list[int] = []
        while not writer_finished.is_set() or not sizes:
            snapshot = registry.snapshot()
            assert isinstance(snapshot, MappingProxyType)
            for oid, codec in snapshot.items():
                offset = oid - base_oid
                assert 0 <= offset < codec_count
                assert codec.oid == oid
                assert codec.name == f"stress_int_{offset}"
            sizes.append(len(snapshot))
            time.sleep(0)
        result.record(("reader", tuple(sizes)))

    stress = run_threads_synchronized(8, worker)
    assert_no_errors(stress)
    readers = [sizes for kind, sizes in stress.results if kind == "reader"]
    assert len(readers) == 7
    assert all(list(sizes) == sorted(sizes) for sizes in readers)
    assert len(registry.snapshot()) == codec_count


@pytest.mark.issue(259)
def test_codec_registry_conflicting_register_fails_loud() -> None:
    registry = build_default_registry()
    codec_a = registry.snapshot()[OID_INT4]
    assert codec_a is not None

    from chirp.data.drivers._pelt._codecs import _int_codec

    conflicting = _int_codec(OID_INT4, "int4_conflict", 4)
    with pytest.raises(ValueError, match="conflicting codec"):
        registry.register(conflicting)


@pytest.mark.issue(259)
@pytest.mark.skipif(
    not _runtime.is_free_threading_enabled(),
    reason="requires a free-threaded build with GIL disabled",
)
def test_default_registry_lazy_init_is_thread_safe() -> None:
    seen: set[int] = set()
    lock = threading.Lock()

    def worker(_index: int, barrier: threading.Barrier, result) -> None:
        barrier.wait()
        registry = _codecs.DEFAULT_REGISTRY
        with lock:
            seen.add(id(registry))
        result.record(registry.snapshot()[OID_INT4].name)  # type: ignore[union-attr]

    stress = run_threads_synchronized(8, worker)
    assert_no_errors(stress)
    assert len(seen) == 1
    assert all(name == "int4" for name in stress.results)


@pytest.mark.issue(259)
async def test_pool_checkout_is_exclusive_under_task_contention() -> None:
    connections = [_YieldingConnection(index) for index in range(4)]
    pool = Pool(cast(Any, connections))
    active: set[int] = set()
    active_lock = anyio.Lock()

    async def worker() -> None:
        conn = cast(_YieldingConnection, await pool.acquire())
        async with active_lock:
            assert conn.identifier not in active
            active.add(conn.identifier)
        await anyio.sleep(0)
        async with active_lock:
            active.remove(conn.identifier)
        await pool.release(cast(Any, conn))

    async with anyio.create_task_group() as task_group:
        for _ in range(64):
            task_group.start_soon(worker)

    assert active == set()
    assert sum(conn.reset_count for conn in connections) == 64
    await pool.close()


@pytest.mark.issue(259)
async def test_pool_does_not_republish_connection_until_reset_finishes() -> None:
    conn = _BlockingResetConnection()
    pool = Pool([cast(Any, conn)])
    checked_out = await pool.acquire()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(pool.release, checked_out)
        await conn.reset_started.wait()

        with anyio.move_on_after(0.05) as acquire_scope:
            await pool.acquire()
        assert acquire_scope.cancel_called

        conn.allow_reset.set()

    reacquired = await pool.acquire()
    assert reacquired is conn
    assert conn.reset_finished is True
    await pool.release(reacquired)
    await pool.close()
