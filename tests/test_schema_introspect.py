"""Live-database round-trip tests for the makemigrations pipeline.

The ROOT CAUSE of the previously-dead migration auto-generator was zero
integration coverage: ``tests/test_schema.py`` only ever exercised
parse/diff/operation_to_sql against synthetic ``SchemaSnapshot`` objects and
never called :func:`introspect` against a real database. These tests close
that gap — ``introspect()`` is run against a real SQLite connection so a
regression to a nonexistent ``Database`` method (the original
``db.fetch_rows()`` / ``db._driver_name`` bug) fails here, not in production.
"""

import os

import pytest

from chirp.data.database import Database
from chirp.data.schema import diff_schemas, generate_migration, introspect, parse_schema
from chirp.data.schema.generate import operation_to_sql
from chirp.data.schema.introspect import introspect_postgres, introspect_sqlite
from chirp.data.schema.operations import AddColumn, CreateTable, DropColumn

# Live PostgreSQL round-trip coverage. The SQLite path above runs everywhere;
# the PostgreSQL path only has live coverage when a DSN is configured (the
# dedicated ``test-postgres`` CI job sets ``CHIRP_TEST_PG_DSN`` against a real
# Postgres service). Without a DSN these tests skip — so local SQLite-only runs
# and the free-threaded main test job stay green.
PG_DSN = os.environ.get("CHIRP_TEST_PG_DSN")
requires_pg = pytest.mark.skipif(
    not PG_DSN,
    reason="CHIRP_TEST_PG_DSN not set — PostgreSQL round-trip coverage skipped",
)


async def test_introspect_smoke_memory() -> None:
    """introspect() runs against in-memory SQLite without AttributeError.

    This is the smoke test that catches the original dead-on-arrival bug:
    introspect() called db.fetch_rows() (nonexistent) and read db._driver_name
    (wrong attribute), so it AttributeError'd on the first call.
    """
    db = Database("sqlite:///:memory:")
    await db.connect()
    try:
        snapshot = await introspect(db)
    finally:
        await db.disconnect()
    # Fresh in-memory DB: no user tables.
    assert snapshot.tables == {}


async def test_fetch_raw_returns_dicts() -> None:
    """fetch_raw is the documented row-access contract: rows are dicts."""
    db = Database("sqlite:///:memory:")
    await db.connect()
    try:
        rows = await db.fetch_raw("SELECT 1 AS one, 'x' AS letter")
    finally:
        await db.disconnect()
    assert rows == [{"one": 1, "letter": "x"}]


async def test_introspect_sqlite_roundtrip(tmp_path) -> None:
    """Create tables, introspect them, and verify columns/PK/FK/index round-trip."""
    db = Database(f"sqlite:///{tmp_path / 'app.db'}")
    await db.connect()
    try:
        await db.execute_script(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT
            );
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE UNIQUE INDEX idx_users_email ON users(email);
            """
        )
        snapshot = await introspect(db)
    finally:
        await db.disconnect()

    assert set(snapshot.tables) == {"users", "posts"}

    users = snapshot.tables["users"]
    assert set(users.columns) == {"id", "name", "email"}
    assert users.columns["id"].primary_key is True
    assert users.columns["name"].nullable is False
    assert users.columns["email"].nullable is True

    posts = snapshot.tables["posts"]
    assert len(posts.foreign_keys) == 1
    fk = posts.foreign_keys[0]
    assert (fk.column, fk.ref_table, fk.ref_column) == ("user_id", "users", "id")

    assert "idx_users_email" in snapshot.indexes
    assert snapshot.indexes["idx_users_email"].unique is True
    assert snapshot.indexes["idx_users_email"].columns == ("email",)


async def test_introspect_then_diff_is_stable(tmp_path) -> None:
    """introspect -> diff against the same desired schema produces no operations."""
    schema_sql = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    """
    db = Database(f"sqlite:///{tmp_path / 'app.db'}")
    await db.connect()
    try:
        await db.execute_script(schema_sql)
        current = await introspect(db)
    finally:
        await db.disconnect()

    desired = parse_schema(schema_sql)
    # The diff is name/structure based; an introspected DB diffed against the
    # schema that created it should be a no-op for table/column presence.
    from chirp.data.schema.operations import CreateTable, DropColumn, DropTable

    ops = diff_schemas(current, desired)
    structural = [
        op for op in ops if isinstance(op, (AddColumn, DropColumn, DropTable, CreateTable))
    ]
    assert structural == []


async def test_makemigrations_pipeline_roundtrip(tmp_path) -> None:
    """Full introspect -> diff -> generate against a real DB produces a .sql file."""
    db = Database(f"sqlite:///{tmp_path / 'app.db'}")
    await db.connect()
    try:
        await db.execute_script("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);")
        current = await introspect(db)
    finally:
        await db.disconnect()

    # Desired schema adds a new table — the diff should emit a CreateTable.
    desired = parse_schema(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, label TEXT NOT NULL);
        """
    )
    ops = diff_schemas(current, desired)
    assert any(isinstance(op, CreateTable) and op.name == "tags" for op in ops)

    migrations_dir = tmp_path / "migrations"
    path = generate_migration(ops, str(migrations_dir))
    assert path is not None
    content = (migrations_dir / path.split("/")[-1]).read_text()
    assert "CREATE TABLE tags" in content


async def test_makemigrations_pipeline_add_drop_column_drift(tmp_path) -> None:
    """Full introspect -> diff -> generate emits the expected ADD/DROP COLUMN drift.

    The CREATE TABLE round-trip is covered above; this anchors the ALTER axis
    against an in-memory SQLite DB so a regression in introspect's column read
    (the original dead-on-arrival path) shows up as a missing drift statement in
    the generated .sql, not as a silent no-op migration.
    """
    db = Database("sqlite:///:memory:")
    await db.connect()
    try:
        await db.execute_script(
            "CREATE TABLE board (id INTEGER PRIMARY KEY, title TEXT NOT NULL, legacy TEXT);"
        )
        current = await introspect(db)
    finally:
        await db.disconnect()

    # Round-trip the live schema: 'legacy' is dropped, 'archived' is added.
    assert set(current.tables["board"].columns) == {"id", "title", "legacy"}

    desired = parse_schema(
        "CREATE TABLE board (id INTEGER PRIMARY KEY, title TEXT NOT NULL, archived INTEGER);"
    )
    ops = diff_schemas(current, desired)

    assert any(
        isinstance(op, AddColumn) and op.table == "board" and op.name == "archived" for op in ops
    )
    assert any(
        isinstance(op, DropColumn) and op.table == "board" and op.name == "legacy" for op in ops
    )

    migrations_dir = tmp_path / "migrations"
    path = generate_migration(ops, str(migrations_dir))
    assert path is not None
    content = (migrations_dir / path.split("/")[-1]).read_text()
    assert "ALTER TABLE board ADD COLUMN archived" in content
    assert "ALTER TABLE board DROP COLUMN legacy;" in content


def test_drop_column_sql_carries_sqlite_warning() -> None:
    """Generated DROP COLUMN SQL carries a hand-edit warning marker."""
    from chirp.data.schema.operations import DropColumn

    sql = operation_to_sql(DropColumn(table="users", name="legacy"))
    assert "WARNING" in sql
    assert "ALTER TABLE users DROP COLUMN legacy;" in sql


def _one_col_snapshot(col_type: str):
    from chirp.data.schema.types import ColumnSchema, SchemaSnapshot, TableSchema

    return SchemaSnapshot(
        tables={
            "users": TableSchema(
                name="users",
                columns={"id": ColumnSchema(name="id", type=col_type)},
            )
        },
    )


def test_diff_warns_on_real_column_type_change() -> None:
    """A genuine column type change is surfaced (warning), never silently dropped."""
    with pytest.warns(UserWarning, match="type change"):
        diff_schemas(_one_col_snapshot("INTEGER"), _one_col_snapshot("TEXT"))


def test_diff_no_warning_for_canonical_type_aliases() -> None:
    """Introspected vs parsed aliases (SERIAL/INTEGER, VARCHAR(n)/CHARACTER VARYING)
    must NOT produce a spurious type-change warning on in-sync schemas."""
    import warnings

    for current_type, desired_type in [
        ("integer", "SERIAL"),  # Postgres introspect 'integer' vs DDL 'SERIAL'
        ("character varying", "VARCHAR(255)"),
        ("timestamp without time zone", "TIMESTAMP"),
        ("boolean", "BOOL"),
        ("numeric", "DECIMAL(10,2)"),
    ]:
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any UserWarning would raise
            diff_schemas(_one_col_snapshot(current_type), _one_col_snapshot(desired_type))


def test_introspect_unknown_driver_raises() -> None:
    """introspect() fails loud on an unsupported driver rather than guessing."""
    import asyncio

    class _Stub:
        _driver = "mysql"

    with pytest.raises(ValueError, match="does not support driver"):
        asyncio.run(introspect(_Stub()))


async def test_introspect_sqlite_direct_helper(tmp_path) -> None:
    """introspect_sqlite works when called directly (used by tooling)."""
    db = Database(f"sqlite:///{tmp_path / 'app.db'}")
    await db.connect()
    try:
        await db.execute_script("CREATE TABLE t (id INTEGER PRIMARY KEY);")
        snapshot = await introspect_sqlite(db)
    finally:
        await db.disconnect()
    assert "t" in snapshot.tables


# ---------------------------------------------------------------------------
# Live PostgreSQL round-trip (gated on CHIRP_TEST_PG_DSN; see the skip guard).
#
# These close the second half of the acceptance criterion for issue #143: the
# introspect -> diff -> generate pipeline must round-trip on *both* backends in
# CI. introspect_postgres reads tables + columns (name/type/nullable/default)
# from information_schema — it does not introspect PK/FK/index metadata — so the
# assertions below cover exactly that surface and no more.
# ---------------------------------------------------------------------------


async def _drop_mig_tables(db: Database) -> None:
    """Idempotent teardown so the suite is rerunnable against a persistent DB."""
    # Child table first to respect the FK; CASCADE belt-and-braces.
    await db.execute("DROP TABLE IF EXISTS mig_posts CASCADE")
    await db.execute("DROP TABLE IF EXISTS mig_tags CASCADE")
    await db.execute("DROP TABLE IF EXISTS mig_users CASCADE")


@requires_pg
async def test_introspect_postgres_roundtrip() -> None:
    """introspect() auto-dispatches to Postgres and round-trips columns + nullability.

    This is the Postgres mirror of test_introspect_sqlite_roundtrip and the
    live coverage the original dead-on-arrival introspect_postgres never had.
    """
    db = Database(PG_DSN)
    await db.connect()
    try:
        assert db._driver == "postgresql"
        await _drop_mig_tables(db)
        await db.execute_script(
            """
            CREATE TABLE mig_users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT
            );
            CREATE TABLE mig_posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES mig_users(id),
                title TEXT NOT NULL
            );
            """
        )

        # Auto-detected dispatch (introspect) and the direct helper agree.
        snapshot = await introspect(db)
        direct = await introspect_postgres(db)

        assert {"mig_users", "mig_posts"} <= set(snapshot.tables)
        assert set(snapshot.tables) == set(direct.tables)

        users = snapshot.tables["mig_users"]
        assert set(users.columns) == {"id", "name", "email"}
        assert users.columns["name"].nullable is False
        assert users.columns["email"].nullable is True

        posts = snapshot.tables["mig_posts"]
        assert set(posts.columns) == {"id", "user_id", "title"}
        assert posts.columns["user_id"].nullable is False
    finally:
        try:
            await _drop_mig_tables(db)
        finally:
            await db.disconnect()


@requires_pg
async def test_makemigrations_pipeline_postgres_roundtrip(tmp_path) -> None:
    """Full introspect -> diff -> generate against a real Postgres DB.

    Introspecting a live schema and diffing it against a desired schema that
    adds a table emits a CreateTable (and, crucially, no spurious drift on the
    unchanged table — proving the SERIAL/INTEGER alias and PK-not-introspected
    cases do not produce false structural ops on Postgres).
    """
    db = Database(PG_DSN)
    await db.connect()
    try:
        assert db._driver == "postgresql"
        await _drop_mig_tables(db)
        await db.execute_script(
            "CREATE TABLE mig_users (id SERIAL PRIMARY KEY, name TEXT NOT NULL);"
        )
        current = await introspect(db)
    finally:
        # Keep the schema diff deterministic, then clean up.
        try:
            await _drop_mig_tables(db)
        finally:
            await db.disconnect()

    desired = parse_schema(
        """
        CREATE TABLE mig_users (id SERIAL PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE mig_tags (id SERIAL PRIMARY KEY, label TEXT NOT NULL);
        """
    )
    ops = diff_schemas(current, desired)

    # The new table is added...
    assert any(isinstance(op, CreateTable) and op.name == "mig_tags" for op in ops)
    # ...and the unchanged table is NOT dropped or column-drifted (no false drift
    # from SERIAL<->INTEGER aliasing or the un-introspected primary key).
    from chirp.data.schema.operations import DropColumn, DropTable

    assert not any(isinstance(op, DropTable) and op.name == "mig_users" for op in ops)
    assert not any(
        isinstance(op, (DropColumn, AddColumn)) and op.table == "mig_users" for op in ops
    )

    migrations_dir = tmp_path / "migrations"
    path = generate_migration(ops, str(migrations_dir))
    assert path is not None
    content = (migrations_dir / path.split("/")[-1]).read_text()
    assert "CREATE TABLE mig_tags" in content
