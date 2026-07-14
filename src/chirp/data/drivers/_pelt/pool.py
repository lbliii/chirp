"""Connection pool for pelt (epic E5).

Mirrors :class:`~chirp.data.drivers.sqlite.SqlitePool`'s ``acquire`` / ``release`` / ``close`` /
``size`` shape so the ``Database`` facade treats both backends uniformly.
"""

from __future__ import annotations

from collections.abc import Sequence

import anyio

from chirp.data.drivers._pelt.connection import Connection
from chirp.data.drivers._pelt.types import ConnectionConfig, PoolConfig


class Pool:
    """A bounded pool of :class:`Connection` instances."""

    __slots__ = ("_all", "_available", "_lock", "_semaphore")

    def __init__(self, connections: Sequence[Connection]) -> None:
        conns = list(connections)
        self._all: list[Connection] = conns
        self._available: list[Connection] = list(conns)
        self._semaphore = anyio.Semaphore(len(conns))
        self._lock = anyio.Lock()

    @property
    def size(self) -> int:
        """Total number of connections managed by the pool."""
        return len(self._all)

    async def acquire(self) -> Connection:
        """Check out a connection, blocking until one is free."""
        await self._semaphore.acquire()
        async with self._lock:
            return self._available.pop()

    async def release(self, conn: Connection) -> None:
        """Return a previously acquired connection to the pool."""
        await conn.reset_if_needed()
        async with self._lock:
            self._available.append(conn)
        self._semaphore.release()

    async def close(self) -> None:
        """Close every connection in the pool."""
        for conn in self._all:
            await conn.close()
        self._available.clear()
        self._all.clear()


async def create_pool(config: PoolConfig) -> Pool:
    """Create a bounded pool of authenticated PostgreSQL connections."""
    size = max(1, config.max_size)
    connections: list[Connection] = []
    try:
        for _ in range(size):
            conn = await Connection.connect(
                config.connection,
                statement_cache_size=config.statement_cache_size,
            )
            connections.append(conn)
    except BaseException:
        for conn in connections:
            await conn.close()
        raise
    return Pool(connections)


async def connect(dsn: str, *, statement_cache_size: int = 100) -> Connection:
    """Open a standalone connection (LISTEN/NOTIFY, scripts)."""
    config = ConnectionConfig.from_dsn(dsn)
    return await Connection.connect(config, statement_cache_size=statement_cache_size)


__all__ = ["Pool", "connect", "create_pool"]
