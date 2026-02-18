"""Async SQLite wrapper using stdlib sqlite3 + anyio.

Zero external dependencies for SQLite support. Runs all blocking sqlite3
calls in a worker thread via ``anyio.to_thread``.

Uses Python 3.12+ features:
    - ``check_same_thread=False``: safe for anyio's thread pool dispatch
    - ``autocommit=True``: individual statements auto-commit; chirp's
      ``transaction()`` context manager flips to manual mode as needed

Free-threading note (3.14t):
    ``check_same_thread=False`` is required because ``anyio.to_thread``
    dispatches to a pool — different calls may land on different threads.
    SQLite in WAL mode with serialized threading handles this safely.
"""

import sqlite3
from collections.abc import Callable, Sequence
from typing import Any

import anyio


def _run_sync(func: Callable[..., Any], *args: Any) -> Any:
    """Run blocking call in anyio worker thread. Wrapper for ty compatibility."""
    return anyio.to_thread.run_sync(func, *args)  # type: ignore[union-attr]


class AsyncCursor:
    """Async wrapper around ``sqlite3.Cursor``."""

    __slots__ = ("_cursor",)

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    @property
    def description(self) -> Any:
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    async def fetchall(self) -> list[Any]:
        return await _run_sync(self._cursor.fetchall)

    async def fetchone(self) -> Any:
        return await _run_sync(self._cursor.fetchone)

    async def fetchmany(self, size: int = 100) -> list[Any]:
        return await _run_sync(lambda: self._cursor.fetchmany(size))


class AsyncConnection:
    """Async wrapper around ``sqlite3.Connection``."""

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def row_factory(self) -> Any:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, factory: Any) -> None:
        self._conn.row_factory = factory

    @property
    def autocommit(self) -> bool:
        return bool(self._conn.autocommit)

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        self._conn.autocommit = value

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> AsyncCursor:
        cursor = await _run_sync(lambda: self._conn.execute(sql, params))
        return AsyncCursor(cursor)

    async def executemany(self, sql: str, params_seq: Sequence[Sequence[Any]]) -> AsyncCursor:
        cursor = await _run_sync(lambda: self._conn.executemany(sql, params_seq))
        return AsyncCursor(cursor)

    async def executescript(self, sql: str) -> None:
        """Execute multiple SQL statements at once.

        Useful for migrations with multiple statements (CREATE + INDEX, etc.).
        Note: ``executescript`` implicitly commits any pending transaction
        before running, and does not honor ``autocommit`` mode.
        """
        await _run_sync(lambda: self._conn.executescript(sql))

    async def commit(self) -> None:
        await _run_sync(self._conn.commit)

    async def rollback(self) -> None:
        await _run_sync(self._conn.rollback)

    async def close(self) -> None:
        await _run_sync(self._conn.close)


async def connect(path: str) -> AsyncConnection:
    """Open an async SQLite connection.

    Uses ``autocommit=True`` so individual statements commit immediately.
    Uses ``check_same_thread=False`` for safe use with anyio's thread pool.
    """
    conn = await _run_sync(lambda: sqlite3.connect(path, autocommit=True, check_same_thread=False))
    return AsyncConnection(conn)
