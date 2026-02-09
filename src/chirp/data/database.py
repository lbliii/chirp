"""Typed async database access.

Supports SQLite (via stdlib ``sqlite3`` + ``anyio``) and PostgreSQL (via ``asyncpg``).
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

import asyncio
import contextlib
import sys
import threading
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, overload

import anyio

from chirp.data._mapping import map_row, map_rows
from chirp.data.errors import (
    DataError,
    DriverNotInstalledError,
    QueryError,
)

# Per-task connection tracking (free-threading safe via ContextVar).
# Set inside transaction() — query methods check this to reuse the
# transaction's connection instead of acquiring a new one from the pool.
_current_conn: ContextVar[Any] = ContextVar("chirp_db_conn")

# App-level database accessor (set by App during lifespan startup).
_db_var: ContextVar[Database] = ContextVar("chirp_db")


def get_db() -> Database:
    """Return the app-level database instance.

    Available when a ``Database`` is configured on the ``App``::

        app = App(db="sqlite:///app.db")

        @app.route("/users")
        async def users():
            db = get_db()
            return await db.fetch(User, "SELECT * FROM users")

    Raises ``LookupError`` if no database is configured or the app
    has not started yet.
    """
    return _db_var.get()


def _in_transaction() -> bool:
    """Check if the current task is inside a managed transaction."""
    try:
        _current_conn.get()
        return True
    except LookupError:
        return False


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database connection configuration.

    Parsed from a URL string or constructed directly.
    """

    url: str
    pool_size: int = 5
    echo: bool = False


@dataclass(frozen=True, slots=True)
class Notification:
    """A notification received from PostgreSQL LISTEN/NOTIFY.

    Attributes:
        channel: The notification channel name.
        payload: The notification payload string (may be empty).
    """

    channel: str
    payload: str


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

        # Transaction (atomic multi-statement)
        async with db.transaction():
            await db.execute("INSERT INTO users ...", name, email)
            await db.execute("INSERT INTO profiles ...", user_id)
    """

    __slots__ = ("_async_lock", "_config", "_driver", "_initialized", "_lock", "_pool")

    def __init__(self, url: str, /, *, pool_size: int = 5, echo: bool = False) -> None:
        self._config = DatabaseConfig(url=url, pool_size=pool_size, echo=echo)
        self._driver = _detect_driver(url)
        self._lock = threading.Lock()
        self._async_lock: anyio.Lock | None = None  # Created lazily on first use
        self._pool: Any = None
        self._initialized = False

    # -- Connection management --

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[Any]:
        """Acquire a connection, release when done.

        If inside a ``transaction()`` block, reuses the transaction's
        connection (no acquire/release — the transaction owns it).
        Otherwise acquires from the pool and releases on exit.

        SQLite connections are serialized via an async lock to prevent
        concurrent thread-pool dispatches on the same connection — matching
        the serialization guarantee that ``aiosqlite`` provided via its
        dedicated thread.
        """
        if not self._initialized:
            await self.connect()

        # Inside a transaction — reuse its connection (lock already held)
        try:
            conn = _current_conn.get()
            yield conn
            return
        except LookupError:
            pass

        # Acquire fresh connection from pool
        if self._driver == "sqlite":
            # Lazy-init the async lock (can't create in __init__ before
            # an event loop exists).
            if self._async_lock is None:
                self._async_lock = anyio.Lock()
            async with self._async_lock:
                yield self._pool  # SQLite: pool IS the connection
        else:
            conn = await self._pool.acquire()
            try:
                yield conn
            finally:
                await self._pool.release(conn)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Execute multiple statements atomically.

        Auto-commits on clean exit, rolls back on exception.
        Calls to ``execute``, ``fetch``, etc. inside the block reuse
        the transaction's connection automatically via ContextVar.

        Nesting is transparent — if already inside a transaction,
        the inner ``transaction()`` joins the outer one (no-op).

        Usage::

            async with db.transaction():
                await db.execute("INSERT INTO users ...", name, email)
                await db.execute("INSERT INTO profiles ...", user_id)
                # auto-commits here

            async with db.transaction():
                await db.execute("INSERT INTO users ...", name, email)
                raise ValueError("oops")
                # auto-rollback on exception
        """
        if not self._initialized:
            await self.connect()

        # Nested transaction — join the existing one (no-op)
        if _in_transaction():
            yield
            return

        # Top-level transaction — acquire a dedicated connection
        if self._driver == "sqlite":
            if self._async_lock is None:
                self._async_lock = anyio.Lock()
            async with self._async_lock:
                conn = self._pool
                token = _current_conn.set(conn)
                try:
                    conn.autocommit = False
                    yield
                    await conn.commit()
                except BaseException:
                    await conn.rollback()
                    raise
                finally:
                    conn.autocommit = True
                    _current_conn.reset(token)
        else:
            conn = await self._pool.acquire()
            token = _current_conn.set(conn)
            try:
                tr = conn.transaction()
                await tr.start()
                yield
                await tr.commit()
            except BaseException:
                await tr.rollback()
                raise
            finally:
                _current_conn.reset(token)
                await self._pool.release(conn)

    # -- Echo / query logging --

    def _log_query(self, sql: str, params: tuple[Any, ...] | Sequence[Any], elapsed: float) -> None:
        """Log a query to stderr when echo is enabled."""
        if not self._config.echo:
            return
        ms = elapsed * 1000
        param_str = f"  params={params!r}" if params else ""
        print(f"[chirp.data] {ms:6.1f}ms  {sql}{param_str}", file=sys.stderr)

    # -- Public query API --

    async def fetch[T](self, cls: type[T], sql: str, /, *params: Any) -> list[T]:
        """Execute a query and return all rows as typed dataclasses.

        Usage::

            users = await db.fetch(User, "SELECT * FROM users WHERE active = ?", True)
        """
        t0 = time.perf_counter()
        async with self._connection() as conn:
            try:
                rows = await _execute_fetch_all(self._driver, conn, sql, params)
                return map_rows(cls, rows)
            except Exception as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._log_query(sql, params, time.perf_counter() - t0)

    async def fetch_one[T](self, cls: type[T], sql: str, /, *params: Any) -> T | None:
        """Execute a query and return the first row, or ``None``.

        Usage::

            user = await db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 42)
        """
        t0 = time.perf_counter()
        async with self._connection() as conn:
            try:
                row = await _execute_fetch_one(self._driver, conn, sql, params)
                if row is None:
                    return None
                return map_row(cls, row)
            except Exception as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._log_query(sql, params, time.perf_counter() - t0)

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
        t0 = time.perf_counter()
        async with self._connection() as conn:
            try:
                async for row in _execute_stream(self._driver, conn, sql, params, batch_size):
                    yield map_row(cls, row)
            except Exception as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._log_query(sql, params, time.perf_counter() - t0)

    async def execute(self, sql: str, /, *params: Any) -> int:
        """Execute a statement (INSERT/UPDATE/DELETE) and return rows affected.

        Usage::

            count = await db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                "Alice", "alice@example.com",
            )
        """
        t0 = time.perf_counter()
        async with self._connection() as conn:
            try:
                return await _execute_statement(self._driver, conn, sql, params)
            except Exception as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._log_query(sql, params, time.perf_counter() - t0)

    async def execute_script(self, sql: str, /) -> None:
        """Execute multiple SQL statements at once (SQLite only).

        Useful for migrations that contain multiple statements::

            await db.execute_script('''
                CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
                CREATE INDEX idx_users_name ON users(name);
            ''')

        For PostgreSQL, use ``execute()`` with individual statements
        inside a ``transaction()`` block instead.
        """
        t0 = time.perf_counter()
        async with self._connection() as conn:
            try:
                if self._driver == "sqlite":
                    await conn.executescript(sql)
                else:
                    # PostgreSQL handles multi-statement SQL natively
                    await conn.execute(sql)
            except Exception as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._log_query(sql, (), time.perf_counter() - t0)

    async def execute_many(
        self,
        sql: str,
        params_seq: Sequence[tuple[Any, ...]],
        /,
    ) -> int:
        """Execute a statement for each parameter set (batch INSERT/UPDATE).

        Returns the total number of rows affected.

        Usage::

            await db.execute_many(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                [("Alice", "a@b.com"), ("Bob", "b@b.com")],
            )
        """
        t0 = time.perf_counter()
        async with self._connection() as conn:
            try:
                return await _execute_many(self._driver, conn, sql, params_seq)
            except Exception as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._log_query(sql, params_seq, time.perf_counter() - t0)

    @overload
    async def fetch_val(self, sql: str, /, *params: Any) -> Any: ...
    @overload
    async def fetch_val[T](self, sql: str, /, *params: Any, as_type: type[T]) -> T | None: ...

    async def fetch_val(self, sql: str, /, *params: Any, as_type: type | None = None) -> Any:
        """Execute a query and return the first column of the first row.

        Useful for COUNT, SUM, MAX, etc.

        Usage::

            count = await db.fetch_val("SELECT COUNT(*) FROM users")
        """
        t0 = time.perf_counter()
        async with self._connection() as conn:
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
            finally:
                self._log_query(sql, params, time.perf_counter() - t0)

    # -- LISTEN/NOTIFY (PostgreSQL only) --

    async def listen(self, *channels: str) -> AsyncIterator[Notification]:
        """Listen for PostgreSQL NOTIFY events on one or more channels.

        Opens a **dedicated connection** (not from the pool) that stays
        open for the lifetime of the iterator.  Yields ``Notification``
        objects as they arrive.

        Pair with chirp's ``EventStream`` for real-time HTML updates::

            @app.route("/orders/live")
            async def live_orders(request):
                async def generate():
                    async for note in app.db.listen("new_orders"):
                        order = await app.db.fetch_one(
                            Order, "SELECT * FROM orders WHERE id = $1",
                            int(note.payload),
                        )
                        if order:
                            yield Fragment("orders.html", "row", order=order)
                return EventStream(generate())

        SQLite does not support LISTEN/NOTIFY — raises ``DataError``.
        """
        if self._driver == "sqlite":
            msg = (
                "LISTEN/NOTIFY is a PostgreSQL feature. "
                "SQLite does not support real-time notifications."
            )
            raise DataError(msg)

        if not self._initialized:
            await self.connect()

        if not channels:
            msg = "listen() requires at least one channel name"
            raise DataError(msg)

        try:
            import asyncpg
        except ImportError:
            msg = (
                "chirp.data requires 'asyncpg' for PostgreSQL LISTEN/NOTIFY. "
                "Install it with: pip install chirp[data-pg]"
            )
            raise DriverNotInstalledError(msg) from None

        # Open a dedicated connection for LISTEN (not from pool)
        conn = await asyncpg.connect(self._config.url)
        queue: asyncio.Queue[Notification] = asyncio.Queue()

        def _on_notify(
            conn: Any,
            pid: int,
            channel: str,
            payload: str,
        ) -> None:
            queue.put_nowait(Notification(channel=channel, payload=payload))

        try:
            for channel in channels:
                await conn.add_listener(channel, _on_notify)

            while True:
                notification = await queue.get()
                yield notification
        finally:
            for channel in channels:
                with contextlib.suppress(Exception):
                    await conn.remove_listener(channel, _on_notify)
            await conn.close()

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

    # -- Context manager --

    async def __aenter__(self) -> Database:
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
    if url.startswith(("postgresql", "postgres")):
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
    import sqlite3

    from chirp.data._sqlite import connect as sqlite_connect

    path = _parse_sqlite_path(config.url)
    conn = await sqlite_connect(path)
    conn.row_factory = sqlite3.Row
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


async def _execute_many(
    driver: str,
    conn: Any,
    sql: str,
    params_seq: Sequence[tuple[Any, ...]],
) -> int:
    if driver == "sqlite":
        cursor = await conn.executemany(sql, params_seq)
        return cursor.rowcount

    # PostgreSQL — asyncpg's executemany returns None, count manually
    await conn.executemany(sql, params_seq)
    return len(params_seq)


async def _execute_statement(driver: str, conn: Any, sql: str, params: tuple[Any, ...]) -> int:
    if driver == "sqlite":
        cursor = await conn.execute(sql, params)
        return cursor.rowcount

    # PostgreSQL
    result = await conn.execute(sql, *params)
    # asyncpg returns "INSERT 0 1" style strings
    parts = result.split()
    if len(parts) >= 3:
        return int(parts[-1])
    return 0
