"""Tests for schema migration system."""

from chirp.data.schema.diff import diff_schemas
from chirp.data.schema.generate import operation_to_sql
from chirp.data.schema.operations import AddColumn, CreateTable, DropColumn, DropTable
from chirp.data.schema.parse import parse_schema
from chirp.data.schema.types import ColumnSchema, SchemaSnapshot, TableSchema


def test_parse_create_table():
    sql = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE
    );
    """
    snapshot = parse_schema(sql)
    assert "users" in snapshot.tables
    assert "id" in snapshot.tables["users"].columns
    assert "name" in snapshot.tables["users"].columns
    assert snapshot.tables["users"].columns["id"].primary_key


def test_parse_create_index():
    sql = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        email TEXT NOT NULL
    );
    CREATE UNIQUE INDEX idx_users_email ON users (email);
    """
    snapshot = parse_schema(sql)
    assert "idx_users_email" in snapshot.indexes
    assert snapshot.indexes["idx_users_email"].unique


def test_diff_add_table():
    current = SchemaSnapshot()
    desired = SchemaSnapshot(
        tables={
            "users": TableSchema(
                name="users",
                columns={"id": ColumnSchema(name="id", type="INTEGER", primary_key=True)},
            )
        }
    )
    ops = diff_schemas(current, desired)
    assert len(ops) == 1
    assert isinstance(ops[0], CreateTable)


def test_diff_drop_table():
    current = SchemaSnapshot(
        tables={
            "old_table": TableSchema(name="old_table", columns={}),
        }
    )
    desired = SchemaSnapshot()
    ops = diff_schemas(current, desired)
    assert len(ops) == 1
    assert isinstance(ops[0], DropTable)


def test_diff_add_column():
    current = SchemaSnapshot(
        tables={
            "users": TableSchema(
                name="users",
                columns={"id": ColumnSchema(name="id", type="INTEGER")},
            )
        }
    )
    desired = SchemaSnapshot(
        tables={
            "users": TableSchema(
                name="users",
                columns={
                    "id": ColumnSchema(name="id", type="INTEGER"),
                    "email": ColumnSchema(name="email", type="TEXT", nullable=False),
                },
            )
        }
    )
    ops = diff_schemas(current, desired)
    assert len(ops) == 1
    assert isinstance(ops[0], AddColumn)
    assert ops[0].name == "email"


def test_diff_drop_column():
    current = SchemaSnapshot(
        tables={
            "users": TableSchema(
                name="users",
                columns={
                    "id": ColumnSchema(name="id", type="INTEGER"),
                    "obsolete": ColumnSchema(name="obsolete", type="TEXT"),
                },
            )
        }
    )
    desired = SchemaSnapshot(
        tables={
            "users": TableSchema(
                name="users",
                columns={"id": ColumnSchema(name="id", type="INTEGER")},
            )
        }
    )
    ops = diff_schemas(current, desired)
    assert len(ops) == 1
    assert isinstance(ops[0], DropColumn)


def test_operation_to_sql_add_column():
    op = AddColumn(table="users", name="email", type="TEXT", nullable=False, default="''")
    sql = operation_to_sql(op)
    assert "ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''" in sql


def test_operation_to_sql_drop_table():
    op = DropTable(name="old_table")
    sql = operation_to_sql(op)
    assert sql == "DROP TABLE old_table;"


def test_no_changes():
    snapshot = SchemaSnapshot(
        tables={
            "users": TableSchema(
                name="users",
                columns={"id": ColumnSchema(name="id", type="INTEGER")},
            )
        }
    )
    ops = diff_schemas(snapshot, snapshot)
    assert ops == []
