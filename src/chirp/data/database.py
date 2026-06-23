"""Typed async database access.

Supports SQLite (via stdlib ``sqlite3`` + ``anyio``) and PostgreSQL (via in-tree ``pelt``).
SQL in, frozen dataclasses out.

Connection URL format::

    sqlite:///path/to/db.sqlite    # SQLite file
    sqlite:///:memory:             # In-memory SQLite
    postgresql://user:pass@host/db # PostgreSQL

Free-threading safety:
    - Connection pool uses ``anyio.Lock`` for async-safe initialization
    - Connections are per-task (ContextVar), never shared between tasks
    - All public methods are async — no sync I/O on the calling thread

Concurrency model:
    - SQLite uses a small bounded pool (sized by ``pool_size``) of WAL-mode
      connections. Readers acquire any free connection and run concurrently;
      write transactions serialize behind ``_sqlite_lock`` (single-writer).
    - PostgreSQL uses asyncpg's native pool with transaction-level isolation.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, overload

import anyio

from chirp.data._mapping import map_row, map_rows
from chirp.data.drivers import postgres as _pg_driver
from chirp.data.drivers import sqlite as _sqlite_driver
from chirp.data.errors import (
    DataError,
    QueryError,
)
from chirp.data.query import json_path as _json_path
from chirp.data.types import DatabaseConfig, Notification

_log = logging.getLogger("chirp.data")

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

    __slots__ = ("_config", "_driver", "_init_lock", "_initialized", "_pool", "_sqlite_lock")

    def __init__(
        self,
        url: str,
        /,
        *,
        pool_size: int = 5,
        echo: bool = False,
        connect_timeout: float = 30.0,
        connect_retries: int = 0,
    ) -> None:
        self._config = DatabaseConfig(
            url=url,
            pool_size=pool_size,
            echo=echo,
            connect_timeout=connect_timeout,
            connect_retries=connect_retries,
        )
        self._driver = _detect_driver(url)
        self._init_lock = anyio.Lock()
        self._sqlite_lock = anyio.Lock()
        self._pool: Any = None
        self._initialized = False

    # -- Connection management --

    @asynccontextmanager
    async def _connection(self, *, write: bool = False) -> AsyncIterator[Any]:
        """Acquire a connection, release when done.

        If inside a ``transaction()`` block, reuses the transaction's
        connection (no acquire/release — the transaction owns it).
        Otherwise acquires from the pool and releases on exit.

        Both backends use a real bounded pool: readers acquire any free pooled
        connection and run concurrently up to ``pool_size``. For SQLite, reads
        no longer take the app-wide write lock — WAL mode lets many readers run
        alongside a single writer. ``write=True`` callers (autocommit
        INSERT/UPDATE/DELETE and ``transaction()``) serialize behind
        ``_sqlite_lock`` to honor SQLite's single-writer model; readers never
        wait on it.
        """
        if not self._initialized:
            await self.connect()

        # Inside a transaction — reuse its connection (the transaction owns it,
        # and the write lock — if any — is already held by the transaction).
        try:
            conn = _current_conn.get()
            yield conn
            return
        except LookupError:
            pass

        # SQLite writers serialize on the app-wide write lock (single writer);
        # file-backed readers and all PostgreSQL access acquire lock-free. An
        # in-memory SQLite DB is a single shared connection, so *every* access
        # (reads included) must serialize on the lock to avoid concurrent
        # thread-pool dispatch on one connection.
        if self._driver == "sqlite" and (write or self._pool.is_memory):
            async with self._sqlite_lock:
                conn = await self._pool.acquire()
                try:
                    yield conn
                finally:
                    await self._pool.release(conn)
            return

        # Acquire a fresh connection from the pool (both backends).
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

        # Top-level transaction — acquire a dedicated connection from the pool.
        if self._driver == "sqlite":
            # SQLite allows N concurrent readers + a single writer (WAL), so the
            # write lock is scoped to write transactions only — reads outside a
            # transaction never wait on it. The lock serializes writers against
            # each other for the whole transaction body (single-writer model).
            async with self._sqlite_lock:
                conn = await self._pool.acquire()
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
                    await self._pool.release(conn)
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

    @asynccontextmanager
    async def _pinned_connection(self) -> AsyncIterator[Any]:
        """Pin one pooled connection for a sequence of writes.

        Acquires a single connection (holding the SQLite write lock for the
        whole block) and binds it via ``_current_conn`` so every nested
        ``execute``/``execute_script`` call reuses the *same* connection. The
        migration runner needs this: a multi-statement script wraps its own
        ``BEGIN``/``COMMIT``, and on failure the ROLLBACK must land on the
        connection that opened the transaction — never a different pooled one
        (which would leave the aborted transaction dangling on a connection
        handed back to the next acquirer).

        Unlike :meth:`transaction` this does *not* toggle autocommit or
        auto-commit/rollback; the caller owns the transaction boundaries.
        """
        if not self._initialized:
            await self.connect()

        # Join an already-pinned connection (transaction or outer pin).
        if _in_transaction():
            yield _current_conn.get()
            return

        if self._driver == "sqlite":
            async with self._sqlite_lock:
                conn = await self._pool.acquire()
                token = _current_conn.set(conn)
                try:
                    yield conn
                finally:
                    _current_conn.reset(token)
                    await self._pool.release(conn)
        else:
            conn = await self._pool.acquire()
            token = _current_conn.set(conn)
            try:
                yield conn
            finally:
                _current_conn.reset(token)
                await self._pool.release(conn)

    # -- Echo / query logging --

    def _log_query(self, sql: str, params: tuple[Any, ...] | Sequence[Any], elapsed: float) -> None:
        """Log a query via the ``chirp.data`` logger when echo is enabled."""
        if not self._config.echo:
            return
        ms = elapsed * 1000
        param_str = f"  params={params!r}" if params else ""
        _log.debug("%6.1fms  %s%s", ms, sql, param_str)

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
        async with self._connection(write=True) as conn:
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
        async with self._connection(write=True) as conn:
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
        async with self._connection(write=True) as conn:
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

    async def fetch_raw(self, sql: str, /, *params: Any) -> list[dict[str, Any]]:
        """Execute a query and return rows as plain ``dict``s — no dataclass mapping.

        This is the documented low-level row-access contract for queries that
        have no fixed result dataclass: schema introspection, ``PRAGMA`` output,
        and other dynamic-column reads. Each row is a ``{column_name: value}``
        dict on both the SQLite and PostgreSQL backends.

        Prefer :meth:`fetch`/:meth:`fetch_one` with a ``frozen=True`` dataclass
        for application queries; ``fetch_raw`` exists for tooling that cannot
        know its columns ahead of time.

        Usage::

            rows = await db.fetch_raw("PRAGMA table_info(users)")
        """
        t0 = time.perf_counter()
        async with self._connection() as conn:
            try:
                return await _execute_fetch_all(self._driver, conn, sql, params)
            except Exception as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._log_query(sql, params, time.perf_counter() - t0)

    # -- Readiness probe --

    async def probe(self) -> bool:
        """Readiness probe — can the pool serve a trivial query?

        Runs ``SELECT 1`` on a **fresh pooled connection** (acquired via
        ``self._connection()``, released on exit), never the request session or
        a live ``transaction()`` connection. A probe must never reuse a possibly
        poisoned request-scoped connection — it asks "is the database reachable
        right now?", independent of any in-flight request's transaction state.

        Returns ``True`` when the query succeeds, ``False`` on any error
        (connection refused, pool exhausted, driver error). Never raises — it is
        wired into the ``/ready`` probe via ``app.add_health_check`` and a raise
        would surface as the check's failure message either way, but returning a
        plain bool keeps the probe's contract simple.

        Auto-wired into ``/ready`` when a db is attached to the app; db-less apps
        never call it.
        """
        try:
            async with self._connection() as conn:
                await _execute_fetch_one(self._driver, conn, "SELECT 1", ())
            return True
        except Exception:
            return False

    # -- JSON path helper --

    def json_path(self, column: str, /, *keys: str) -> str:
        """Build a dialect-correct JSON-extraction SQL expression fragment.

        Convenience wrapper over :func:`chirp.data.json_path` that supplies this
        database's active driver as the dialect, so call sites never hand-branch
        on sqlite-vs-postgres::

            where_clause = db.json_path("oauth", "sub") + " = ?"
            user = await db.fetch_one(User, f"SELECT * FROM users WHERE {where_clause}", sub_id)

        On SQLite this emits ``json_extract(oauth, '$.sub')``; on PostgreSQL it
        emits ``oauth->>'sub'``. The expression contains no bound-parameter
        placeholder of its own — keep filter values as separate bound params and
        **never** pass request/user values as ``column`` or ``keys`` (they are
        concatenated into the SQL text, not parameterized).
        """
        return _json_path(column, *keys, dialect=self._driver)

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

        from chirp.data.drivers._pelt.pool import connect as pelt_connect

        conn = await pelt_connect(self._config.url)
        queue: asyncio.Queue[Notification] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _enqueue_notification(channel: str, payload: str) -> None:
            queue.put_nowait(Notification(channel=channel, payload=payload))

        def _on_notify(
            _conn: Any,
            _pid: int,
            channel: str,
            payload: str,
        ) -> None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(_enqueue_notification, channel, payload)

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
        to fail fast at startup. Uses connect_timeout and connect_retries
        from config for resilience.
        """
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            cfg = self._config
            last_exc: BaseException | None = None
            for attempt in range(cfg.connect_retries + 1):
                try:
                    self._pool = await asyncio.wait_for(
                        _create_pool(self._driver, cfg),
                        timeout=cfg.connect_timeout,
                    )
                    self._initialized = True
                    return
                except TimeoutError as e:
                    last_exc = e
                except BaseException as e:
                    last_exc = e
                    if attempt == cfg.connect_retries:
                        raise
            if last_exc is not None:
                raise last_exc

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if not self._initialized:
            return
        async with self._init_lock:
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


async def _create_pool(driver: str, config: DatabaseConfig) -> Any:
    if driver == "sqlite":
        return await _sqlite_driver.create_pool(config)
    return await _pg_driver.create_pool(config)


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
