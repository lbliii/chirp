"""Connection pool for pelt (epic E5).

Mirrors :class:`~chirp.data.drivers.sqlite.SqlitePool`'s ``acquire`` / ``release`` / ``close`` /
``size`` shape so the ``Database`` facade treats both backends uniformly.

Pool construction acquires a process-wide :class:`~._type_discovery.TypeCatalogCache`
keyed by host/port/database so checkouts reuse warmed ``pg_catalog`` metadata
(#953). Closing the pool releases that shared reference.
"""

from __future__ import annotations

from collections.abc import Sequence

import anyio

from chirp.data.drivers._pelt import _type_discovery
from chirp.data.drivers._pelt.connection import Connection
from chirp.data.drivers._pelt.types import ConnectionConfig, PoolConfig


class Pool:
    """A bounded pool of :class:`Connection` instances."""

    __slots__ = ("_all", "_available", "_lock", "_semaphore", "_type_catalog")

    def __init__(
        self,
        connections: Sequence[Connection],
        *,
        type_catalog: _type_discovery.TypeCatalogCache | None = None,
    ) -> None:
        conns = list(connections)
        self._all: list[Connection] = conns
        self._available: list[Connection] = list(conns)
        self._semaphore = anyio.Semaphore(len(conns))
        self._lock = anyio.Lock()
        self._type_catalog = type_catalog

    @property
    def size(self) -> int:
        """Total number of connections managed by the pool."""
        return len(self._all)

    @property
    def type_catalog(self) -> _type_discovery.TypeCatalogCache | None:
        """Shared warm type-catalog cache for this pool, if any."""
        return self._type_catalog

    async def acquire(self) -> Connection:
        """Check out a connection, blocking until one is free.

        Exhaustion is a bounded wait on the pool semaphore — never a shared
        borrow. Concurrent Suspense independent defers that each ``acquire``
        therefore hold distinct connections (#950). Size the pool
        (``PoolConfig.max_size`` / ``Database(..., pool_size=...)``) to the
        peak concurrent checkouts you need, or accept queueing latency when
        more defers contend than connections exist.
        """
        await self._semaphore.acquire()
        async with self._lock:
            return self._available.pop()

    async def release(self, conn: Connection) -> None:
        """Return a previously acquired connection to the pool.

        Reset I/O finishes before the connection is republished, so the pool
        lock is never held across await boundaries for callers that release
        promptly after each defer query.
        """
        await conn.reset_if_needed()
        async with self._lock:
            self._available.append(conn)
        self._semaphore.release()

    async def close(self) -> None:
        """Close every connection and release the shared type-catalog cache."""
        for conn in self._all:
            await conn.close()
        self._available.clear()
        self._all.clear()
        catalog = self._type_catalog
        self._type_catalog = None
        if catalog is not None:
            _type_discovery.release_type_catalog_cache(catalog)

    def reset_type_catalog(self) -> None:
        """Invalidate the warm type-catalog snapshot (explicit pool reset)."""
        catalog = self._type_catalog
        if catalog is not None:
            catalog.invalidate()


async def create_pool(config: PoolConfig) -> Pool:
    """Create a bounded pool of authenticated PostgreSQL connections.

    Acquires the process-wide type-catalog cache for the pool's connection
    target at construction time so worker startup can warm once and every
    checkout reuses the immutable snapshot.
    """
    size = max(1, config.max_size)
    catalog = _type_discovery.acquire_type_catalog_cache(
        config.connection.host,
        config.connection.port,
        config.connection.database,
    )
    connections: list[Connection] = []
    try:
        for _ in range(size):
            conn = await Connection.connect(
                config.connection,
                statement_cache_size=config.statement_cache_size,
                type_catalog=catalog,
            )
            connections.append(conn)
    except BaseException:
        for conn in connections:
            await conn.close()
        _type_discovery.release_type_catalog_cache(catalog)
        raise
    return Pool(connections, type_catalog=catalog)


async def connect(dsn: str, *, statement_cache_size: int = 100) -> Connection:
    """Open a standalone connection (LISTEN/NOTIFY, scripts)."""
    config = ConnectionConfig.from_dsn(dsn)
    return await Connection.connect(config, statement_cache_size=statement_cache_size)


__all__ = ["Pool", "connect", "create_pool"]
