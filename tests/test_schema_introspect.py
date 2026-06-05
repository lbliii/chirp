"""Live-database round-trip tests for the makemigrations pipeline.

The ROOT CAUSE of the previously-dead migration auto-generator was zero
integration coverage: ``tests/test_schema.py`` only ever exercised
parse/diff/operation_to_sql against synthetic ``SchemaSnapshot`` objects and
never called :func:`introspect` against a real database. These tests close
that gap — ``introspect()`` is run against a real SQLite connection so a
regression to a nonexistent ``Database`` method (the original
``db.fetch_rows()`` / ``db._driver_name`` bug) fails here, not in production.
"""

import pytest

from chirp.data.database import Database
from chirp.data.schema import diff_schemas, generate_migration, introspect, parse_schema
from chirp.data.schema.generate import operation_to_sql
from chirp.data.schema.introspect import introspect_sqlite
from chirp.data.schema.operations import AddColumn, CreateTable


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
