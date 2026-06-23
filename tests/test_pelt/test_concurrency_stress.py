"""E6 (#259) — free-threading hardening and concurrency proof for pelt."""

from __future__ import annotations

import threading

import pytest

from chirp.data.drivers._pelt import _codecs, _runtime
from chirp.data.drivers._pelt._codecs import OID_INT4, build_default_registry
from chirp.data.drivers._pelt._messages import FieldDescription, RowDescription
from chirp.data.drivers._pelt.connection import _decode_rows
from tests.test_concurrency.conftest import assert_no_errors, run_threads_synchronized


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
def test_codec_registry_concurrent_snapshot_reads() -> None:
    registry = build_default_registry()

    def worker(_index: int, barrier: threading.Barrier, result) -> None:
        barrier.wait()
        snapshot = registry.snapshot()
        result.record(len(snapshot))

    stress = run_threads_synchronized(8, worker)
    assert_no_errors(stress)
    assert all(count > 0 for count in stress.results)


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
