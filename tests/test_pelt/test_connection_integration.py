"""E5 (#258) — pelt round-trip tests against live PostgreSQL."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import anyio
import pytest

from chirp.data.database import Database
from chirp.data.drivers._pelt import connection as pelt_connection
from chirp.data.drivers._pelt import pool as pelt_pool
from chirp.data.drivers._pelt._codecs_composite_range_enum import Range
from chirp.data.drivers._pelt._codecs_temporal import Interval
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
@pytest.mark.issue(260)
async def test_database_stream_resumes_across_multiple_portal_batches() -> None:
    assert PG_DSN is not None
    db = Database(PG_DSN)
    await db.connect()
    try:
        streamed = [
            row
            async for row in db.stream(
                IdRow,
                "SELECT generate_series(1, 5) AS id",
                batch_size=2,
            )
        ]
    finally:
        await db.disconnect()

    assert streamed == [IdRow(1), IdRow(2), IdRow(3), IdRow(4), IdRow(5)]


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


@requires_pg
@pytest.mark.issue(260)
async def test_live_leaf_codec_matrix() -> None:
    """Every registered leaf family decodes an actual PostgreSQL text result."""
    assert PG_DSN is not None
    conn = await pelt_pool.connect(PG_DSN)
    try:
        await conn.execute("SET TIME ZONE 'UTC'")
        row = await conn.fetchrow(
            """
            SELECT
                32767::int2 AS small_int,
                2147483647::int4 AS integer,
                9223372036854775807::int8 AS big_int,
                1.25::float4 AS single_float,
                2.5::float8 AS double_float,
                true::bool AS flag,
                'plain'::text AS plain_text,
                'varying'::varchar AS varying_text,
                'fixed'::char(5) AS fixed_text,
                12345.6789::numeric AS exact_number,
                DATE '2024-01-02' AS calendar_date,
                TIME '12:34:56.123456' AS wall_time,
                TIMESTAMP '2024-01-02 03:04:05.123456' AS local_timestamp,
                TIMESTAMPTZ '2024-01-02 03:04:05.123456+00' AS utc_timestamp,
                TIMETZ '12:34:56.123456+02' AS zoned_time,
                '12345678-1234-5678-1234-567812345678'::uuid AS identifier,
                decode('00ff10', 'hex') AS binary_value,
                '{"kind":"json","count":2}'::json AS json_value,
                '{"kind":"jsonb","active":true}'::jsonb AS jsonb_value
            """
        )
    finally:
        await conn.close()

    assert row is not None
    assert dict(row) == {
        "small_int": 32767,
        "integer": 2147483647,
        "big_int": 9223372036854775807,
        "single_float": 1.25,
        "double_float": 2.5,
        "flag": True,
        "plain_text": "plain",
        "varying_text": "varying",
        "fixed_text": "fixed",
        "exact_number": Decimal("12345.6789"),
        "calendar_date": date(2024, 1, 2),
        "wall_time": time(12, 34, 56, 123456),
        "local_timestamp": datetime(2024, 1, 2, 3, 4, 5, 123456),
        "utc_timestamp": datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=UTC),
        "zoned_time": time(12, 34, 56, 123456, tzinfo=timezone(timedelta(hours=2))),
        "identifier": UUID("12345678-1234-5678-1234-567812345678"),
        "binary_value": b"\x00\xff\x10",
        "json_value": {"kind": "json", "count": 2},
        "jsonb_value": {"kind": "jsonb", "active": True},
    }


@requires_pg
@pytest.mark.issue(260)
async def test_live_array_and_range_types_preserve_text_when_binary_is_not_requested() -> None:
    """Arrays and ranges stay lossless strings on the current text-result path."""
    assert PG_DSN is not None
    conn = await pelt_pool.connect(PG_DSN)
    try:
        row = await conn.fetchrow(
            """
            SELECT
                ARRAY[1, 2, NULL]::int4[] AS numbers,
                int4range(1, 4, '[)') AS span
            """
        )
    finally:
        await conn.close()

    assert row is not None
    assert dict(row) == {
        "numbers": "{1,2,NULL}",
        "span": "[1,4)",
    }


@requires_pg
@pytest.mark.issue(695)
async def test_live_extended_query_negotiates_dynamic_types_and_text_fallback() -> None:
    """Server-assigned OIDs drive one mixed Bind without changing cached declaration facts."""
    assert PG_DSN is not None
    conn = await pelt_pool.connect(PG_DSN)
    sql = """
        SELECT
            $1::int4 AS integer,
            'happy'::pelt_695_mood AS mood,
            ARRAY['happy'::pelt_695_mood, NULL, 'sad'::pelt_695_mood] AS moods,
            ROW(9, 'sad')::pelt_695_card AS card,
            '[happy,sad]'::pelt_695_mood_range AS mood_span,
            '0/16B6C50'::pg_lsn AS opaque_known_to_postgres
    """
    try:
        await conn.execute(
            "DROP TYPE IF EXISTS pelt_695_mood_range, pelt_695_card, pelt_695_mood CASCADE"
        )
        await conn.execute("CREATE TYPE pelt_695_mood AS ENUM ('happy', 'sad')")
        await conn.execute("CREATE TYPE pelt_695_card AS (rank int4, mood pelt_695_mood)")
        await conn.execute("CREATE TYPE pelt_695_mood_range AS RANGE (subtype=pelt_695_mood)")

        first = await conn.fetchrow(sql, 7)
        statement = conn._protocol.cache.get(sql, ())
        attempted = frozenset(conn._catalog_attempted_oids)
        second = await conn.fetchrow(sql, 8)
        reused = conn._protocol.cache.get(sql, ())

        assert first is not None
        assert dict(first) == {
            "integer": 7,
            "mood": "happy",
            "moods": ["happy", None, "sad"],
            "card": (9, "sad"),
            "mood_span": Range("happy", "sad", lower_inc=True, upper_inc=True),
            "opaque_known_to_postgres": "0/16B6C50",
        }
        assert second is not None
        assert second["integer"] == 8
        assert statement is not None
        assert reused is statement
        assert statement.row_description is not None
        assert tuple(field.format_code for field in statement.row_description.fields) == (
            0,
            0,
            0,
            0,
            0,
            0,
        )
        assert conn._active_row_description is not None
        assert tuple(field.format_code for field in conn._active_row_description.fields) == (
            1,
            0,
            1,
            1,
            1,
            0,
        )
        assert frozenset(conn._catalog_attempted_oids) == attempted
        fields_by_name = {field.name: field for field in statement.row_description.fields}
        registry = conn._registry.snapshot()
        assert registry[fields_by_name["mood"].type_oid].prefers_binary is False
        for name in ("moods", "card", "mood_span"):
            assert registry[fields_by_name[name].type_oid].prefers_binary is True
        assert registry.get(fields_by_name["opaque_known_to_postgres"].type_oid) is None
        result_oids = {field.type_oid for field in fields_by_name.values()}
        assert result_oids <= conn._catalog_attempted_oids | set(conn._registry.snapshot())
    finally:
        await conn.execute(
            "DROP TYPE IF EXISTS pelt_695_mood_range, pelt_695_card, pelt_695_mood CASCADE"
        )
        await conn.close()


@requires_pg
@pytest.mark.issue(695)
@pytest.mark.parametrize(
    "interval_style",
    ["sql_standard", "postgres", "postgres_verbose", "iso_8601"],
)
async def test_live_binary_interval_is_independent_of_interval_style(
    interval_style: str,
) -> None:
    assert PG_DSN is not None
    conn = await pelt_pool.connect(PG_DSN)
    sql = """
        SELECT
            $1::int4 AS marker,
            INTERVAL '1 year 2 months 3 days 04:05:06.123456' AS span
    """
    try:
        await conn.execute(f"SET IntervalStyle TO '{interval_style}'")
        row = await conn.fetchrow(sql, 1)
    finally:
        await conn.close()

    assert row is not None
    assert row["marker"] == 1
    assert row["span"] == Interval(
        months=14,
        days=3,
        microseconds=((4 * 60 + 5) * 60 + 6) * 1_000_000 + 123_456,
    )
    assert conn._active_row_description is not None
    assert tuple(field.format_code for field in conn._active_row_description.fields) == (1, 1)


@requires_pg
@pytest.mark.issue(260)
async def test_listen_notify_delivery_unsubscribe_and_close() -> None:
    """A live listener keeps one reader across queries, unsubscribe, and close."""
    assert PG_DSN is not None
    listener = await pelt_pool.connect(PG_DSN)
    sender = await pelt_pool.connect(PG_DSN)
    channel = "pelt_e7_conformance"
    other_channel = "pelt_e7_conformance_other"
    received: list[tuple[str, str]] = []
    first_delivered = anyio.Event()
    other_delivered = anyio.Event()
    other_after_unlisten = anyio.Event()

    def on_notify(
        _connection: pelt_connection.Connection,
        _pid: int,
        notified_channel: str,
        payload: str,
    ) -> None:
        received.append((notified_channel, payload))
        if payload == "first":
            first_delivered.set()

    def on_other_notify(
        _connection: pelt_connection.Connection,
        _pid: int,
        notified_channel: str,
        payload: str,
    ) -> None:
        received.append((notified_channel, payload))
        if payload == "other":
            other_delivered.set()
        elif payload == "other-after-unlisten":
            other_after_unlisten.set()

    try:
        await listener.add_listener(channel, on_notify)
        await sender.execute("SELECT pg_notify($1, $2)", channel, "first")
        with anyio.fail_after(5):
            await first_delivered.wait()

        row = await listener.fetchrow("SELECT 1 AS still_queryable")
        assert dict(row) == {"still_queryable": 1}

        await listener.add_listener(other_channel, on_other_notify)
        await sender.execute("SELECT pg_notify($1, $2)", other_channel, "other")
        with anyio.fail_after(5):
            await other_delivered.wait()

        assert received == [(channel, "first"), (other_channel, "other")]

        await listener.remove_listener(channel, on_notify)
        await sender.execute("SELECT pg_notify($1, $2)", channel, "after-unlisten")
        await sender.execute("SELECT pg_notify($1, $2)", other_channel, "other-after-unlisten")
        with anyio.fail_after(5):
            await other_after_unlisten.wait()
        await anyio.sleep(0.1)
        assert received == [
            (channel, "first"),
            (other_channel, "other"),
            (other_channel, "other-after-unlisten"),
        ]

        await listener.remove_listener(other_channel, on_other_notify)
        await sender.execute("SELECT pg_notify($1, $2)", other_channel, "after-all-unlisten")
        await anyio.sleep(0.1)
        assert received[-1] == (other_channel, "other-after-unlisten")
    finally:
        await listener.close()
        await sender.close()

    assert listener._closed is True
    assert listener._listener_tg is None
