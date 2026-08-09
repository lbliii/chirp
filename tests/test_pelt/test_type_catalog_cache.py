"""Issue #953: process-wide immutable type-catalog cache (pool warmup)."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from chirp.data.drivers._pelt import _runtime, _type_discovery
from chirp.data.drivers._pelt._codecs import build_default_registry
from chirp.data.drivers._pelt._messages import RowDescription
from chirp.data.drivers._pelt._protocol import (
    ExtendedQueryProtocol,
    PreparedStatementCache,
    ProtocolState,
    TransactionStatus,
)
from chirp.data.drivers._pelt._transport import PGStream
from chirp.data.drivers._pelt._type_discovery import (
    TypeCatalogCache,
    apply_type_catalog_snapshot,
    clear_type_catalog_caches,
    parse_type_catalog_rows,
)
from chirp.data.drivers._pelt.connection import Connection, Record, _QueryResult
from chirp.data.drivers._pelt.pool import create_pool
from chirp.data.drivers._pelt.types import ConnectionConfig, PoolConfig
from tests.test_concurrency.conftest import assert_no_errors, run_threads_synchronized
from tests.test_pelt.test_type_discovery import (
    COMPOSITE_OID,
    ENUM_ARRAY_OID,
    ENUM_OID,
    RANGE_OID,
    _catalog_row,
    _field,
    _metadata_rows,
)

pytestmark = pytest.mark.issue(953)


@pytest.fixture(autouse=True)
def _isolate_type_catalog_caches() -> None:
    clear_type_catalog_caches()
    yield
    clear_type_catalog_caches()


def _metadata():
    return parse_type_catalog_rows(_metadata_rows())


class _NullStream:
    async def receive(self, max_bytes: int = 65536) -> bytes:
        del max_bytes
        return b""

    async def send(self, data: bytes) -> None:
        del data

    async def aclose(self) -> None:
        return None


class _CountingConnection(Connection):
    """Connection that records catalog SQL instead of speaking the wire protocol."""

    def __init__(self, *, type_catalog: TypeCatalogCache, queries: list[str]) -> None:
        protocol = ExtendedQueryProtocol(
            state=ProtocolState.READY,
            transaction_status=TransactionStatus.IDLE,
            cache=PreparedStatementCache(),
        )
        super().__init__(
            stream=PGStream(stream=_NullStream()),
            protocol=protocol,
            config=ConnectionConfig(host="localhost", port=5432, database="cache_db"),
            type_catalog=type_catalog,
        )
        self._catalog_query_log = queries

    async def _execute_simple(self, sql: str) -> _QueryResult:  # type: ignore[override]
        self._catalog_query_log.append(sql)
        rows = [Record(tuple(row.keys()), tuple(row.values())) for row in _metadata_rows()]
        return _QueryResult(rows=rows, command_tag="SELECT")


def test_type_catalog_cache_warm_is_immutable_and_first_wins() -> None:
    cache = TypeCatalogCache(("localhost", 5432, "app"))
    first = _metadata()
    second = parse_type_catalog_rows((_catalog_row(ENUM_OID, "other.mood", "e"),))

    published = cache.warm(first, (ENUM_OID, ENUM_ARRAY_OID, COMPOSITE_OID, RANGE_OID))
    again = cache.warm(second, (ENUM_OID,))

    assert cache.is_warm is True
    assert again is published
    assert published.by_oid[ENUM_OID].name == "public.mood"
    cache.invalidate()
    assert cache.is_warm is False
    assert cache.snapshot() is None


def test_apply_type_catalog_snapshot_hydrates_connection_local_registry() -> None:
    cache = TypeCatalogCache(("localhost", 5432, "app"))
    metadata = _metadata()
    cache.warm(metadata, tuple(item.oid for item in metadata))
    registry = build_default_registry()
    attempted: set[int] = set()

    apply_type_catalog_snapshot(registry, attempted, cache.snapshot())

    snapshot = registry.snapshot()
    assert ENUM_OID in snapshot
    assert ENUM_ARRAY_OID in snapshot
    assert COMPOSITE_OID in snapshot
    assert RANGE_OID in snapshot
    assert attempted >= {ENUM_OID, ENUM_ARRAY_OID, COMPOSITE_OID, RANGE_OID}


def test_type_catalog_cache_concurrent_reads_are_safe() -> None:
    cache = TypeCatalogCache(("localhost", 5432, "shared"))
    metadata = _metadata()
    cache.warm(metadata, tuple(item.oid for item in metadata))

    def worker(_index: int, barrier: threading.Barrier, result) -> None:
        barrier.wait()
        for _ in range(64):
            snap = cache.snapshot()
            assert snap is not None
            assert snap.by_oid[ENUM_OID].name == "public.mood"
            assert COMPOSITE_OID in snap.attempted_oids
        result.record(True)

    stress = run_threads_synchronized(8, worker)
    assert_no_errors(stress)
    assert stress.results == [True] * 8


@pytest.mark.skipif(
    not _runtime.is_free_threading_enabled(),
    reason="requires a free-threaded build with GIL disabled",
)
def test_type_catalog_cache_concurrent_reads_under_nogil() -> None:
    """PYTHON_GIL=0 receipt: immutable snapshot reads across native threads."""
    assert _runtime.is_free_threading_enabled()
    test_type_catalog_cache_concurrent_reads_are_safe()


async def test_second_checkout_skips_redundant_catalog_queries() -> None:
    """After warmup, a second connection reuses the cache without pg_catalog I/O."""
    catalog_queries: list[str] = []
    description = RowDescription(
        fields=(
            _field("mood", ENUM_OID),
            _field("moods", ENUM_ARRAY_OID),
            _field("card", COMPOSITE_OID),
            _field("mood_span", RANGE_OID),
        )
    )
    cache = _type_discovery.acquire_type_catalog_cache("localhost", 5432, "cache_db")
    first = _CountingConnection(type_catalog=cache, queries=catalog_queries)
    second = _CountingConnection(type_catalog=cache, queries=catalog_queries)

    await first._ensure_result_codecs(description)
    assert catalog_queries, "first checkout must query pg_catalog"
    assert cache.is_warm is True
    first_queries = len(catalog_queries)

    await second._ensure_result_codecs(description)
    assert len(catalog_queries) == first_queries
    assert ENUM_OID in second._registry.snapshot()
    assert second._catalog_attempted_oids >= first._catalog_attempted_oids

    _type_discovery.release_type_catalog_cache(cache)


async def test_create_pool_attaches_shared_cache_and_close_invalidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[Any] = []

    class _StubConnection:
        def __init__(self, *, type_catalog: TypeCatalogCache | None = None) -> None:
            self.type_catalog = type_catalog
            self.closed = False

        @classmethod
        async def connect(
            cls,
            config: ConnectionConfig,
            *,
            statement_cache_size: int,
            type_catalog: TypeCatalogCache | None = None,
        ) -> _StubConnection:
            del config, statement_cache_size
            conn = cls(type_catalog=type_catalog)
            opened.append(conn)
            return conn

        async def close(self) -> None:
            self.closed = True

        async def reset_if_needed(self) -> None:
            return None

    monkeypatch.setattr("chirp.data.drivers._pelt.pool.Connection", _StubConnection)

    pool = await create_pool(
        PoolConfig(
            connection=ConnectionConfig(host="localhost", port=5432, database="pool_db"),
            min_size=0,
            max_size=2,
        )
    )
    assert pool.type_catalog is not None
    assert pool.type_catalog.identity == ("localhost", 5432, "pool_db")
    assert all(conn.type_catalog is pool.type_catalog for conn in opened)

    pool.type_catalog.warm(_metadata(), (ENUM_OID,))
    assert pool.type_catalog.is_warm is True
    pool.reset_type_catalog()
    assert pool.type_catalog.is_warm is False

    pool.type_catalog.warm(_metadata(), (ENUM_OID,))
    await pool.close()
    assert all(conn.closed for conn in opened)
    assert _type_discovery._CATALOG_CACHES.get(("localhost", 5432, "pool_db")) is None


async def test_pool_close_releases_refcount_without_dropping_sibling_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubConnection:
        def __init__(self, *, type_catalog: TypeCatalogCache | None = None) -> None:
            self.type_catalog = type_catalog

        @classmethod
        async def connect(
            cls,
            config: ConnectionConfig,
            *,
            statement_cache_size: int,
            type_catalog: TypeCatalogCache | None = None,
        ) -> _StubConnection:
            del config, statement_cache_size
            return cls(type_catalog=type_catalog)

        async def close(self) -> None:
            return None

    monkeypatch.setattr("chirp.data.drivers._pelt.pool.Connection", _StubConnection)
    cfg = PoolConfig(
        connection=ConnectionConfig(host="localhost", port=5432, database="shared_db"),
        min_size=0,
        max_size=1,
    )
    first = await create_pool(cfg)
    second = await create_pool(cfg)
    assert first.type_catalog is second.type_catalog
    assert first.type_catalog is not None
    first.type_catalog.warm(_metadata(), (ENUM_OID,))

    await first.close()
    assert second.type_catalog is not None
    assert second.type_catalog.is_warm is True

    await second.close()
    assert _type_discovery._CATALOG_CACHES.get(("localhost", 5432, "shared_db")) is None


async def test_create_pool_releases_catalog_on_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[Any] = []

    class _FailingConnection:
        def __init__(self, *, type_catalog: TypeCatalogCache | None = None) -> None:
            self.type_catalog = type_catalog
            self.closed = False

        @classmethod
        async def connect(
            cls,
            config: ConnectionConfig,
            *,
            statement_cache_size: int,
            type_catalog: TypeCatalogCache | None = None,
        ) -> _FailingConnection:
            del config, statement_cache_size
            if opened:
                raise RuntimeError("second connection failed")
            conn = cls(type_catalog=type_catalog)
            opened.append(conn)
            return conn

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("chirp.data.drivers._pelt.pool.Connection", _FailingConnection)

    with pytest.raises(RuntimeError, match="second connection failed"):
        await create_pool(
            PoolConfig(
                connection=ConnectionConfig(host="localhost", port=5432, database="fail_db"),
                min_size=0,
                max_size=2,
            )
        )

    assert opened[0].closed is True
    assert _type_discovery._CATALOG_CACHES.get(("localhost", 5432, "fail_db")) is None
