"""Integration tests for ``chirp makemigrations`` (chirp.cli._makemigrations).

The command had no test coverage — a dead-CLI-command risk. These tests drive
``run_makemigrations`` against a real temp SQLite database and temp schema input
(both ``.sql`` and ``.py`` with a ``SCHEMA`` variable), and exercise every
branch: a generated migration, the no-changes early return, the empty-file
exit-1 branch, and the missing-file exit-1 branch.

``run_makemigrations`` manages its own event loop via ``asyncio.run``, so these
are plain synchronous tests (no ``async def``) to avoid nesting loops.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from chirp.cli._makemigrations import run_makemigrations

# A desired schema with a single table. Run against an empty DB this must
# produce exactly one CREATE TABLE operation.
_SCHEMA_SQL = """
CREATE TABLE widgets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
"""


def _make_args(*, db: str, schema: str, migrations_dir: str) -> SimpleNamespace:
    return SimpleNamespace(db=db, schema=schema, migrations_dir=migrations_dir)


def _empty_sqlite_db(tmp_path: Path) -> str:
    """Create an empty SQLite file and return its sqlite:/// URL."""
    db_file = tmp_path / "app.db"
    # Touch a valid empty SQLite database so introspection sees zero tables.
    conn = sqlite3.connect(db_file)
    conn.close()
    return f"sqlite:///{db_file}"


def _sql_schema_file(tmp_path: Path, body: str = _SCHEMA_SQL) -> Path:
    path = tmp_path / "schema.sql"
    path.write_text(body)
    return path


def _py_schema_file(tmp_path: Path, body: str = _SCHEMA_SQL) -> Path:
    """A Python schema module exposing the SQL via a ``SCHEMA`` variable."""
    path = tmp_path / "schema.py"
    path.write_text(f"SCHEMA = {body!r}\n")
    return path


@pytest.mark.parametrize("schema_kind", ["sql", "py"])
class TestMakemigrationsGenerates:
    def test_generates_migration_file(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        schema_kind: str,
    ) -> None:
        """A non-empty diff writes a numbered .sql migration and prints it."""
        db_url = _empty_sqlite_db(tmp_path)
        schema = _sql_schema_file(tmp_path) if schema_kind == "sql" else _py_schema_file(tmp_path)
        migrations_dir = tmp_path / "migrations"

        run_makemigrations(
            _make_args(db=db_url, schema=str(schema), migrations_dir=str(migrations_dir))
        )

        # A migration file must exist on disk.
        files = sorted(migrations_dir.glob("*.sql"))
        assert len(files) == 1, f"expected one migration, got {files}"
        migration = files[0]
        assert migration.name.startswith("001_")
        contents = migration.read_text()
        assert "CREATE TABLE widgets" in contents

        out = capsys.readouterr().out
        assert "Generated:" in out
        assert str(migration) in out
        # The per-operation SQL summary is printed too.
        assert "CREATE TABLE widgets" in out

    def test_no_changes_early_return(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        schema_kind: str,
    ) -> None:
        """When the DB already matches the schema, nothing is generated."""
        # Pre-create the table so introspection matches the desired schema.
        db_file = tmp_path / "app.db"
        conn = sqlite3.connect(db_file)
        conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conn.commit()
        conn.close()
        db_url = f"sqlite:///{db_file}"

        schema = _sql_schema_file(tmp_path) if schema_kind == "sql" else _py_schema_file(tmp_path)
        migrations_dir = tmp_path / "migrations"

        # No SystemExit: the no-changes path returns normally.
        run_makemigrations(
            _make_args(db=db_url, schema=str(schema), migrations_dir=str(migrations_dir))
        )

        assert "No changes detected." in capsys.readouterr().out
        # No migration directory/files should have been created.
        assert not migrations_dir.exists() or not list(migrations_dir.glob("*.sql"))

    def test_empty_schema_file_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        schema_kind: str,
    ) -> None:
        """A whitespace-only schema source exits 1 before touching the DB."""
        db_url = _empty_sqlite_db(tmp_path)
        schema = (
            _sql_schema_file(tmp_path, body="   \n\t\n")
            if schema_kind == "sql"
            else _py_schema_file(tmp_path, body="   \n\t\n")
        )
        migrations_dir = tmp_path / "migrations"

        with pytest.raises(SystemExit) as exc_info:
            run_makemigrations(
                _make_args(db=db_url, schema=str(schema), migrations_dir=str(migrations_dir))
            )

        assert exc_info.value.code == 1
        assert "Schema file is empty" in capsys.readouterr().out


class TestMakemigrationsMissingFile:
    def test_missing_schema_file_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A nonexistent schema path exits 1 with a clear message."""
        db_url = _empty_sqlite_db(tmp_path)
        missing = tmp_path / "does_not_exist.sql"
        migrations_dir = tmp_path / "migrations"

        with pytest.raises(SystemExit) as exc_info:
            run_makemigrations(
                _make_args(db=db_url, schema=str(missing), migrations_dir=str(migrations_dir))
            )

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Schema file not found" in out
        assert str(missing) in out
