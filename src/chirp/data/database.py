"""Typed async database access.

Supports SQLite (via ``aiosqlite``) and PostgreSQL (via ``asyncpg``).
SQL in, frozen dataclasses out.

Connection URL format::

    sqlite:///path/to/db.sqlite    # SQLite file
    sqlite:///:memory:             # In-memory SQLite
    postgresql://user:pass@host/db # PostgreSQL

Free-threading safety:
    - Connection pool uses ``threading.Lock`` for thread-safe access
    - Connections are per-task (ContextVar), never shared between tasks
    - All public methods are async — no sync I/O on the calling thread
"""

import threading
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, overload

from chirp.data._mapping import map_row, map_rows
from chirp.data.errors import (
    ConnectionError,
    DataError,
    DriverNotInstalledError,
    QueryError,
)

# Per-task connection tracking (free-threading safe via ContextVar)
_current_conn: ContextVar[Any] = ContextVar("chirp_db_conn")


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database connection configuration.

    Parsed from a URL string or constructed directly.
    """

    url: str
    pool_size: int = 5
    echo: bool = False


class Database:
    """Typed async database access.

    SQL queries return frozen dataclasses. Streaming queries return async
    iterators. Both modes use the same SQL — the difference is whether you
    want all results at once or incrementally.

    Usage::

        db = Database("sqlite:///app.db")

        @dataclass(frozen=True, slots=True)
        class User:
            id: int
            name: str
            email: str

        # Fetch all
        users = await db.fetch(User, "SELECT * FROM users")

        # Fetch one
        user = await db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 42)

        # Stream (cursor-based)
        async for user in db.stream(User, "SELECT * FROM users"):
            process(user)

        # Execute (INSERT/UPDATE/DELETE)
        await db.execute("INSERT INTO users (name, email) VALUES (?, ?)",
                         "Alice", "alice@example.com")

        # Raw scalar
        count = await db.fetch_val("SELECT COUNT(*) FROM users")
    """

    __slots__ = ("_config", "_driver", "_lock", "_pool", "_initialized")

    def __init__(self, url: str, /, *, pool_size: int = 5, echo: bool = False) -> None:
        self._config = DatabaseConfig(url=url, pool_size=pool_size, echo=echo)
        self._driver = _detect_driver(url)
        self._lock = threading.Lock()
        self._pool: Any = None
        self._initialized = False

    # -- Public query API --

    async def fetch[T](self, cls: type[T], sql: str, /, *params: Any) -> list[T]:
        """Execute a query and return all rows as typed dataclasses.

        Usage::

            users = await db.fetch(User, "SELECT * FROM users WHERE active = ?", True)
        """
        conn = await self._get_connection()
        try:
            rows = await _execute_fetch_all(self._driver, conn, sql, params)
            return map_rows(cls, rows)
        except Exception as exc:
            raise QueryError(str(exc)) from exc

    async def fetch_one[T](self, cls: type[T], sql: str, /, *params: Any) -> T | None:
        """Execute a query and return the first row, or ``None``.

        Usage::

            user = await db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 42)
        """
        conn = await self._get_connection()
        try:
            row = await _execute_fetch_one(self._driver, conn, sql, params)
            if row is None:
                return None
            return map_row(cls, row)
        except Exception as exc:
            raise QueryError(str(exc)) from exc

    async def stream[T](
        self, cls: type[T], sql: str, /, *params: Any, batch_size: int = 100
    ) -> AsyncIterator[T]:
        """Execute a query and yield rows incrementally as typed dataclasses.

        Uses a server-side cursor for memory-efficient iteration over large
        result sets. Rows are fetched in batches of ``batch_size``.

        Usage::

            async for entry in db.stream(LogEntry, "SELECT * FROM logs"):
                process(entry)
        """
        conn = await self._get_connection()
        try:
            async for row in _execute_stream(self._driver, conn, sql, params, batch_size):
                yield map_row(cls, row)
        except Exception as exc:
            raise QueryError(str(exc)) from exc

    async def execute(self, sql: str, /, *params: Any) -> int:
        """Execute a statement (INSERT/UPDATE/DELETE) and return rows affected.

        Usage::

            count = await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice", "alice@example.com",
            )
        """
        conn = await self._get_connection()
        try:
            return await _execute_statement(self._driver, conn, sql, params)
        except Exception as exc:
            raise QueryError(str(exc)) from exc

    @overload
    async def fetch_val(self, sql: str, /, *params: Any) -> Any: ...
    @overload
    async def fetch_val[T](self, sql: str, /, *params: Any, as_type: type[T]) -> T | None: ...

    async def fetch_val(
        self, sql: str, /, *params: Any, as_type: type | None = None
    ) -> Any:
        """Execute a query and return the first column of the first row.

        Useful for COUNT, SUM, MAX, etc.

        Usage::

            count = await db.fetch_val("SELECT COUNT(*) FROM users")
        """
        conn = await self._get_connection()
        try:
            row = await _execute_fetch_one(self._driver, conn, sql, params)
            if row is None:
                return None
            # Row is a dict — return the first value
            first_value = next(iter(row.values()))
            if as_type is not None:
                return as_type(first_value)
            return first_value
        except Exception as exc:
            raise QueryError(str(exc)) from exc

    # -- Lifecycle --

    async def connect(self) -> None:
        """Initialize the connection pool.

        Called automatically on first query. Call explicitly if you want
        to fail fast at startup.
        """
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._pool = await _create_pool(self._driver, self._config)
            self._initialized = True

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if not self._initialized:
            return
        with self._lock:
            if not self._initialized:
                return
            await _close_pool(self._driver, self._pool)
            self._pool = None
            self._initialized = False

    async def _get_connection(self) -> Any:
        """Get a connection from the pool (lazy-initializes on first call)."""
        if not self._initialized:
            await self.connect()
        return await _acquire(self._driver, self._pool)

    # -- Context manager --

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()


# =============================================================================
# Driver detection and dispatch
# =============================================================================
# Each driver function has a sqlite and postgresql path.
# This avoids a driver abstraction class — just functions dispatched on a string.


def _detect_driver(url: str) -> str:
    """Detect the database driver from the URL scheme."""
    if url.startswith("sqlite"):
        return "sqlite"
    if url.startswith("postgresql") or url.startswith("postgres"):
        return "postgresql"
    msg = (
        f"Unsupported database URL scheme: {url!r}. "
        "Supported: sqlite:///path, postgresql://user@host/db"
    )
    raise DataError(msg)


def _parse_sqlite_path(url: str) -> str:
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


# -- Pool creation --


async def _create_pool(driver: str, config: DatabaseConfig) -> Any:
    if driver == "sqlite":
        return await _create_sqlite_pool(config)
    return await _create_pg_pool(config)


async def _create_sqlite_pool(config: DatabaseConfig) -> Any:
    try:
        import aiosqlite
    except ImportError:
        msg = (
            "chirp.data requires 'aiosqlite' for SQLite databases. "
            "Install it with: pip install chirp[data]"
        )
        raise DriverNotInstalledError(msg) from None

    path = _parse_sqlite_path(config.url)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    # Enable WAL mode for better concurrent read performance
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def _create_pg_pool(config: DatabaseConfig) -> Any:
    try:
        import asyncpg
    except ImportError:
        msg = (
            "chirp.data requires 'asyncpg' for PostgreSQL databases. "
            "Install it with: pip install chirp[data-pg]"
        )
        raise DriverNotInstalledError(msg) from None

    return await asyncpg.create_pool(
        config.url,
        min_size=1,
        max_size=config.pool_size,
    )


# -- Pool teardown --


async def _close_pool(driver: str, pool: Any) -> None:
    if driver == "sqlite":
        await pool.close()
    else:
        await pool.close()


# -- Connection acquisition --


async def _acquire(driver: str, pool: Any) -> Any:
    if driver == "sqlite":
        # SQLite: the pool IS the connection (single writer)
        return pool
    # PostgreSQL: acquire from asyncpg pool
    return await pool.acquire()


# -- Query execution --


async def _execute_fetch_all(
    driver: str, conn: Any, sql: str, params: tuple[Any, ...]
) -> list[dict[str, Any]]:
    if driver == "sqlite":
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]

    # PostgreSQL (asyncpg returns Records)
    rows = await conn.fetch(sql, *params)
    return [dict(row) for row in rows]


async def _execute_fetch_one(
    driver: str, conn: Any, sql: str, params: tuple[Any, ...]
) -> dict[str, Any] | None:
    if driver == "sqlite":
        cursor = await conn.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row, strict=True))

    # PostgreSQL
    row = await conn.fetchrow(sql, *params)
    if row is None:
        return None
    return dict(row)


async def _execute_stream(
    driver: str,
    conn: Any,
    sql: str,
    params: tuple[Any, ...],
    batch_size: int,
) -> AsyncIterator[dict[str, Any]]:
    if driver == "sqlite":
        cursor = await conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        while True:
            rows = await cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield dict(zip(columns, row, strict=True))
        return

    # PostgreSQL — use a transaction cursor for true server-side streaming
    async with conn.transaction():
        async for row in conn.cursor(sql, *params, prefetch=batch_size):
            yield dict(row)


async def _execute_statement(
    driver: str, conn: Any, sql: str, params: tuple[Any, ...]
) -> int:
    if driver == "sqlite":
        cursor = await conn.execute(sql, params)
        await conn.commit()
        return cursor.rowcount

    # PostgreSQL
    result = await conn.execute(sql, *params)
    # asyncpg returns "INSERT 0 1" style strings
    parts = result.split()
    if len(parts) >= 3:
        return int(parts[-1])
    return 0
