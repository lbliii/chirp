"""E5 (#258) — pelt round-trip tests against live PostgreSQL."""

from __future__ import annotations

import os
from dataclasses import dataclass

import anyio
import pytest

from chirp.data.database import Database
from chirp.data.drivers._pelt import connection as pelt_connection
from chirp.data.drivers._pelt import pool as pelt_pool
from chirp.data.drivers._pelt.errors import PostgresError
from chirp.data.drivers._pelt.types import PoolConfig

PG_DSN = os.environ.get("CHIRP_TEST_PG_DSN")
requires_pg = pytest.mark.skipif(
    not PG_DSN,
    reason="CHIRP_TEST_PG_DSN not set — pelt PostgreSQL round-trip coverage skipped",
)


@dataclass(frozen=True, slots=True)
class IdRow:
    id: int


@requires_pg
@pytest.mark.issue(258)
async def test_pelt_pool_acquire_release() -> None:
    db = Database(PG_DSN)
    await db.connect()
    try:
        pool = db._pool
        assert pool.size >= 1
        conn = await pool.acquire()
        try:
            row = await conn.fetchrow("SELECT 1 AS one")
            assert dict(row) == {"one": 1}
        finally:
            await pool.release(conn)
    finally:
        await db.disconnect()


@requires_pg
@pytest.mark.issue(258)
async def test_database_fetch_execute_transaction() -> None:
    db = Database(PG_DSN)
    await db.connect()
    try:
        await db.execute("CREATE TEMP TABLE pelt_e5 (id INT PRIMARY KEY, name TEXT NOT NULL)")
        await db.execute("INSERT INTO pelt_e5 (id, name) VALUES ($1, $2)", 1, "alpha")
        rows = await db.fetch_raw("SELECT id, name FROM pelt_e5 ORDER BY id")
        assert rows == [{"id": 1, "name": "alpha"}]

        async with db.transaction():
            await db.execute("INSERT INTO pelt_e5 (id, name) VALUES ($1, $2)", 2, "beta")
        rows = await db.fetch_raw("SELECT id FROM pelt_e5 ORDER BY id")
        assert rows == [{"id": 1}, {"id": 2}]
    finally:
        await db.disconnect()


@requires_pg
@pytest.mark.issue(258)
async def test_database_executemany_and_stream() -> None:
    db = Database(PG_DSN)
    await db.connect()
    try:
        await db.execute("CREATE TEMP TABLE pelt_e5_many (id INT PRIMARY KEY)")
        await db.execute_many(
            "INSERT INTO pelt_e5_many (id) VALUES ($1)",
            [(1,), (2,), (3,)],
        )
        streamed = [
            row
            async for row in db.stream(
                IdRow,
                "SELECT id FROM pelt_e5_many ORDER BY id",
            )
        ]
        assert streamed == [IdRow(1), IdRow(2), IdRow(3)]
    finally:
        await db.disconnect()


@requires_pg
@pytest.mark.issue(258)
async def test_standalone_connect_and_close() -> None:
    conn = await pelt_pool.connect(PG_DSN)
    try:
        tag = await conn.execute("SELECT 1")
        assert tag.startswith("SELECT")
    finally:
        await conn.close()


@requires_pg
@pytest.mark.issue(258)
def test_record_is_dictable() -> None:
    rec = pelt_connection.Record(("a", "b"), (1, "x"))
    assert dict(rec) == {"a": 1, "b": "x"}


@requires_pg
@pytest.mark.issue(259)
async def test_pool_rolls_back_failed_transaction_before_reuse() -> None:
    assert PG_DSN is not None
    pool = await pelt_pool.create_pool(PoolConfig.from_dsn(PG_DSN, max_size=1))
    conn = await pool.acquire()
    try:
        await conn.execute("BEGIN")
        with pytest.raises(PostgresError) as caught:
            await conn.execute("SELECT 1 / 0")
        assert caught.value.sqlstate == "22012"
    finally:
        await pool.release(conn)

    try:
        reused = await pool.acquire()
        try:
            assert reused is conn
            row = await reused.fetchrow("SELECT 1 AS recovered")
            assert dict(row) == {"recovered": 1}
        finally:
            await pool.release(reused)
    finally:
        await pool.close()


@requires_pg
@pytest.mark.issue(259)
async def test_parallel_checkouts_keep_statement_caches_single_owner() -> None:
    """Each checked-out connection prepares a repeated query exactly once."""
    assert PG_DSN is not None
    pool = await pelt_pool.create_pool(PoolConfig.from_dsn(PG_DSN, max_size=4))
    connections = [await pool.acquire() for _ in range(pool.size)]
    statement_names: list[str] = []
    names_lock = anyio.Lock()
    sql = "SELECT $1::int4 AS value"

    async def exercise(conn: pelt_connection.Connection, value: int) -> None:
        first_row = await conn.fetchrow(sql, value)
        first = conn._protocol.cache.get(sql, ())
        second_row = await conn.fetchrow(sql, value + 10)
        second = conn._protocol.cache.get(sql, ())

        assert dict(first_row) == {"value": value}
        assert dict(second_row) == {"value": value + 10}
        assert first is not None
        assert second is first
        assert len(conn._protocol.cache) == 1
        async with names_lock:
            statement_names.append(first.name)

    try:
        async with anyio.create_task_group() as task_group:
            for index, conn in enumerate(connections):
                task_group.start_soon(exercise, conn, index)
    finally:
        for conn in connections:
            await pool.release(conn)
        await pool.close()

    assert len(statement_names) == 4
    assert set(statement_names) == {"pelt_stmt_1"}
