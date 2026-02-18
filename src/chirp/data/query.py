"""Immutable query builder for chirp.data.

Accumulates SQL clauses through chaining methods, compiles to a SQL string
+ parameters tuple, and executes via the existing ``Database`` methods.

Each method returns a new frozen ``Query`` — the original is never mutated.
Same pattern as ``Response.with_*()`` but for SELECT queries.

Usage::

    from chirp.data import Database, Query

    @dataclass(frozen=True, slots=True)
    class Todo:
        id: int
        text: str
        done: bool

    todos = await (
        Query(Todo, "todos")
        .where("done = ?", False)
        .where_if(search, "text LIKE ?", f"%{search}%")
        .order_by("id DESC")
        .take(20)
        .fetch(db)
    )

Transparency: ``.sql`` and ``.params`` show exactly what will run.
No hidden queries, no magic.

Free-threading safety:
    - Frozen dataclass — immutable after creation
    - Tuple accumulators — no shared mutable state
    - No locks needed
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.data.database import Database


@dataclass(frozen=True, slots=True)
class Query[T]:
    """Immutable SELECT query builder.

    Construct with a target dataclass and table name, chain methods to
    add clauses, then execute via ``fetch()``, ``fetch_one()``, etc.

    Every method returns a new ``Query`` — the original is unchanged.
    """

    _cls: type[T]
    _table: str
    _wheres: tuple[tuple[str, tuple[object, ...]], ...] = ()
    _order: str | None = None
    _limit: int | None = None
    _offset: int | None = None
    _columns: str = "*"

    # ── Building ─────────────────────────────────────────────────────────

    def where(self, clause: str, /, *params: object) -> Query[T]:
        """Add a WHERE clause. Multiple calls are ANDed.

        ::

            Query(Todo, "todos").where("done = ?", False).where("id > ?", 10)
            # WHERE done = ? AND id > ?
        """
        return replace(self, _wheres=(*self._wheres, (clause, params)))

    def where_if(self, condition: object, clause: str, /, *params: object) -> Query[T]:
        """Add a WHERE clause only if ``condition`` is truthy.

        The killer method for dynamic queries — no more string
        concatenation with ``if`` blocks::

            Query(Todo, "todos")
                .where_if(status, "done = ?", status == "done")
                .where_if(search, "text LIKE ?", f"%{search}%")
        """
        if not condition:
            return self
        return self.where(clause, *params)

    def order_by(self, clause: str) -> Query[T]:
        """Set ORDER BY. Replaces any previous ordering.

        ::

            Query(Todo, "todos").order_by("id DESC")
        """
        return replace(self, _order=clause)

    def take(self, n: int) -> Query[T]:
        """Set LIMIT (max rows to return).

        ::

            Query(Todo, "todos").take(20)
        """
        return replace(self, _limit=n)

    def skip(self, n: int) -> Query[T]:
        """Set OFFSET (rows to skip).

        ::

            Query(Todo, "todos").take(20).skip(40)  # page 3
        """
        return replace(self, _offset=n)

    def select(self, columns: str) -> Query[T]:
        """Set which columns to SELECT. Default is ``*``.

        ::

            Query(Todo, "todos").select("id, text")
        """
        return replace(self, _columns=columns)

    # ── Compilation ──────────────────────────────────────────────────────

    @property
    def sql(self) -> str:
        """The exact SQL that will run. No surprises."""
        parts = [f"SELECT {self._columns} FROM {self._table}"]
        if self._wheres:
            clauses = " AND ".join(w[0] for w in self._wheres)
            parts.append(f"WHERE {clauses}")
        if self._order:
            parts.append(f"ORDER BY {self._order}")
        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")
        if self._offset is not None:
            parts.append(f"OFFSET {self._offset}")
        return " ".join(parts)

    @property
    def params(self) -> tuple[object, ...]:
        """The bound parameters, in order."""
        result: list[object] = []
        for _, p in self._wheres:
            result.extend(p)
        return tuple(result)

    # ── Execution ────────────────────────────────────────────────────────

    async def fetch(self, db: Database) -> list[T]:
        """Execute and return all matching rows as typed dataclasses."""
        return await db.fetch(self._cls, self.sql, *self.params)

    async def fetch_one(self, db: Database) -> T | None:
        """Execute and return the first matching row, or ``None``."""
        return await db.fetch_one(self._cls, self.sql, *self.params)

    async def count(self, db: Database) -> int:
        """Execute a COUNT(*) with the same WHERE clauses.

        Ignores ``select()``, ``order_by()``, ``take()``, and ``skip()``
        — counts all matching rows.
        """
        parts = [f"SELECT COUNT(*) FROM {self._table}"]
        if self._wheres:
            clauses = " AND ".join(w[0] for w in self._wheres)
            parts.append(f"WHERE {clauses}")
        sql = " ".join(parts)
        return await db.fetch_val(sql, *self.params, as_type=int) or 0

    async def stream(self, db: Database, *, batch_size: int = 100) -> AsyncIterator[T]:
        """Execute and yield rows incrementally as typed dataclasses."""
        async for row in db.stream(self._cls, self.sql, *self.params, batch_size=batch_size):
            yield row

    async def exists(self, db: Database) -> bool:
        """Check if at least one matching row exists.

        Uses ``SELECT 1 ... LIMIT 1`` for efficiency.
        """
        parts = [f"SELECT 1 FROM {self._table}"]
        if self._wheres:
            clauses = " AND ".join(w[0] for w in self._wheres)
            parts.append(f"WHERE {clauses}")
        parts.append("LIMIT 1")
        sql = " ".join(parts)
        result = await db.fetch_val(sql, *self.params)
        return result is not None
