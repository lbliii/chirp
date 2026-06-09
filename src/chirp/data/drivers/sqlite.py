"""SQLite driver helpers for chirp.data.

For file-backed databases the "pool" is a small bounded set of ``AsyncConnection``
instances. WAL mode (enabled per connection) lets SQLite serve many concurrent
readers alongside a single writer, so readers acquire any pooled connection
without the app-wide write lock; write serialization is handled at the
``Database`` layer.

In-memory databases (``sqlite:///:memory:`` / ``sqlite://``) are special. A
plain ``:memory:`` connection is private to whichever connection opened it, so a
multi-connection pool would hand each task its own empty database. Shared-cache
mode (``file::memory:?cache=shared``) lets connections see one logical database
but uses coarse table-level locks that raise ``SQLITE_LOCKED`` (not retried by
``busy_timeout``) under concurrent reader/writer access. So in-memory databases
use a **single shared connection** (``pool_size`` is treated as 1) and the
``Database`` layer serializes all access — reads included — on ``_sqlite_lock``.
In-memory is a development/test convenience; concurrent-reader throughput is a
file-database (WAL) property. WAL is unavailable for memory DBs (stays
``journal_mode=memory``) so the PRAGMA is skipped there.
"""

from collections.abc import Sequence

import anyio

from chirp.data.errors import DataError
from chirp.data.types import DatabaseConfig


def parse_sqlite_path(url: str) -> str:
    """Extract the file path from a sqlite:// URL."""
    # sqlite:///path/to/db  ->  /path/to/db
    # sqlite:///:memory:    ->  :memory:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        return url[len(prefix) :]
    prefix_short = "sqlite://"
    if url.startswith(prefix_short):
        return url[len(prefix_short) :]
    msg = f"Invalid SQLite URL: {url!r}"
    raise DataError(msg)


def is_memory_path(path: str) -> bool:
    """True when the parsed path refers to an in-memory database.

    Covers ``:memory:`` and the empty path (``sqlite://``), plus any explicit
    ``file:...:memory:...`` shared-cache URI.
    """
    if path in ("", ":memory:"):
        return True
    return path.startswith("file:") and ":memory:" in path


def _connect_target(path: str) -> tuple[str, bool, bool]:
    """Resolve the connection target for a parsed SQLite path.

    Returns ``(target, uri, in_memory)``:

    - ``target`` — the string handed to ``sqlite3.connect``.
    - ``uri`` — whether ``uri=True`` must be passed (shared-cache memory DBs).
    - ``in_memory`` — whether this is an in-memory database (skips WAL).

    In-memory databases collapse to a single shared connection (see module
    docstring), so a plain ``:memory:`` target is sufficient — every query runs
    on that one connection rather than a per-task private empty database.
    """
    if is_memory_path(path):
        if path.startswith("file:"):
            # Caller already supplied a URI form — trust it.
            return path, True, True
        # A single shared connection backs in-memory DBs, so a plain ``:memory:``
        # target is sufficient (and avoids shared-cache table-lock contention).
        return ":memory:", False, True
    return path, False, False


class SqlitePool:
    """A small bounded pool of async SQLite connections.

    Exposes ``acquire()`` / ``release()`` mirroring the asyncpg pool API so the
    ``Database`` facade can treat both backends uniformly. Connections are never
    bound to a task — the ``Database`` layer owns per-task assignment via the
    ``_current_conn`` ContextVar — so a connection handed out by ``acquire()``
    is exclusively held until the matching ``release()``.

    In-memory databases (``is_memory=True``) hold exactly one shared connection
    so every task sees the same logical database; the ``Database`` layer
    serializes all in-memory access (reads included) since a lone SQLite
    connection cannot safely take concurrent thread-pool dispatches.
    """

    __slots__ = ("_all", "_available", "_lock", "_semaphore", "is_memory")

    def __init__(self, connections: Sequence[object], *, is_memory: bool = False) -> None:
        self._all: list[object] = list(connections)
        self._available: list[object] = list(connections)
        # Caps concurrent checkouts at pool_size; the list holds the free conns.
        self._semaphore = anyio.Semaphore(len(self._all))
        self._lock = anyio.Lock()
        # In-memory pools hold a single shared connection; the Database layer
        # serializes all access on _sqlite_lock (reads included).
        self.is_memory = is_memory

    @property
    def size(self) -> int:
        """Total number of connections managed by the pool."""
        return len(self._all)

    async def acquire(self) -> object:
        """Check out a connection, blocking until one is free."""
        await self._semaphore.acquire()
        async with self._lock:
            return self._available.pop()

    async def release(self, conn: object) -> None:
        """Return a previously acquired connection to the pool."""
        async with self._lock:
            self._available.append(conn)
        self._semaphore.release()

    async def close(self) -> None:
        """Close every connection in the pool."""
        for conn in self._all:
            await conn.close()  # type: ignore[attr-defined]
        self._available.clear()
        self._all.clear()


async def create_pool(config: DatabaseConfig) -> SqlitePool:
    """Create a small bounded pool of SQLite connections.

    File-backed pools size by ``config.pool_size`` (minimum 1) with WAL mode per
    connection so SQLite serves concurrent readers alongside a single writer.
    In-memory databases collapse to a single shared connection (skipping WAL,
    which is unavailable for ``:memory:``) so every task sees the same logical
    database; the ``Database`` layer serializes their access.
    """
    import sqlite3

    from chirp.data._sqlite import connect as sqlite_connect

    path = parse_sqlite_path(config.url)
    target, uri, in_memory = _connect_target(path)
    # In-memory DBs use a single shared connection (see module docstring);
    # file DBs use a real bounded pool sized by pool_size.
    size = 1 if in_memory else max(1, config.pool_size)

    connections: list[object] = []
    for _ in range(size):
        conn = await sqlite_connect(target, uri=uri)
        conn.row_factory = sqlite3.Row
        if not in_memory:
            # WAL enables concurrent readers + a single writer on file DBs.
            # It is unavailable for in-memory databases (stays journal=memory).
            await conn.execute("PRAGMA journal_mode=WAL")
            # Wait (rather than raise "database is locked") if another pooled
            # connection briefly holds the write lock during the write handoff.
            await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        connections.append(conn)

    return SqlitePool(connections, is_memory=in_memory)
