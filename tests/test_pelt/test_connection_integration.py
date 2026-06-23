"""E5 (#258) — pelt round-trip tests against live PostgreSQL."""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from chirp.data.database import Database
from chirp.data.drivers._pelt import connection as pelt_connection
from chirp.data.drivers._pelt import pool as pelt_pool

PG_DSN = os.environ.get("CHIRP_TEST_PG_DSN")
requires_pg = pytest.mark.skipif(
    not PG_DSN,
    reason="CHIRP_TEST_PG_DSN not set — pelt PostgreSQL round-trip coverage skipped",
)


@dataclass(frozen=True, slots=True)
class IdRow:
    id: int


@pytest.fixture
async def pg_db() -> Database:
    db = Database(PG_DSN)
    await db.connect()
    try:
        yield db
    finally:
        await db.disconnect()


@requires_pg
@pytest.mark.issue(258)
@pytest.mark.anyio
async def test_pelt_pool_acquire_release(pg_db: Database) -> None:
    pool = pg_db._pool
    assert pool.size >= 1
    conn = await pool.acquire()
    try:
        row = await conn.fetchrow("SELECT 1 AS one")
        assert dict(row) == {"one": 1}
    finally:
        await pool.release(conn)


@requires_pg
@pytest.mark.issue(258)
@pytest.mark.anyio
async def test_database_fetch_execute_transaction(pg_db: Database) -> None:
    await pg_db.execute("CREATE TEMP TABLE pelt_e5 (id INT PRIMARY KEY, name TEXT NOT NULL)")
    await pg_db.execute("INSERT INTO pelt_e5 (id, name) VALUES ($1, $2)", 1, "alpha")
    rows = await pg_db.fetch_raw("SELECT id, name FROM pelt_e5 ORDER BY id")
    assert rows == [{"id": 1, "name": "alpha"}]

    async with pg_db.transaction():
        await pg_db.execute("INSERT INTO pelt_e5 (id, name) VALUES ($1, $2)", 2, "beta")
    rows = await pg_db.fetch_raw("SELECT id FROM pelt_e5 ORDER BY id")
    assert rows == [{"id": 1}, {"id": 2}]


@requires_pg
@pytest.mark.issue(258)
@pytest.mark.anyio
async def test_database_executemany_and_stream(pg_db: Database) -> None:
    await pg_db.execute("CREATE TEMP TABLE pelt_e5_many (id INT PRIMARY KEY)")
    await pg_db.execute_many(
        "INSERT INTO pelt_e5_many (id) VALUES ($1)",
        [(1,), (2,), (3,)],
    )
    streamed = [
        row
        async for row in pg_db.stream(
            IdRow,
            "SELECT id FROM pelt_e5_many ORDER BY id",
        )
    ]
    assert streamed == [IdRow(1), IdRow(2), IdRow(3)]


@requires_pg
@pytest.mark.issue(258)
@pytest.mark.anyio
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
