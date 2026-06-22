"""Integration tests for ``chirp migrate`` (chirp.cli._migrate) — issue #380.

The command applies pending migrations as a one-shot deploy job, mirroring the
sibling ``chirp makemigrations`` flag surface (``--db`` / ``--migrations-dir``).
These tests drive ``run_migrate`` against a real temp SQLite database and a temp
``NNN_*.sql`` migration directory, exercising:

- pending migrations applied + the ``MigrationResult.summary`` printed,
- the already-up-to-date (no pending) path,
- the fail-loud path: a broken migration raises ``MigrationError`` inside the
  runner, which ``run_migrate`` reports and turns into ``SystemExit(1)`` — no
  swallowing.

The acceptance test (``test_issue_380_skip_knob_and_cli``) ties the two success
criteria together: ``CHIRP_SKIP_MIGRATIONS=1`` skips the on-boot run, and
``chirp migrate`` applies pending migrations and fails loud on error.

``run_migrate`` manages its own event loop via ``asyncio.run``, so these are
plain synchronous tests (no ``async def``) to avoid nesting loops.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from chirp.cli._migrate import run_migrate
from chirp.config import AppConfig

_CREATE_WIDGETS = "CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
_CREATE_GADGETS = "CREATE TABLE gadgets (id INTEGER PRIMARY KEY);"


def _make_args(*, db: str, migrations_dir: str) -> SimpleNamespace:
    return SimpleNamespace(db=db, migrations_dir=migrations_dir)


def _empty_sqlite_db(tmp_path: Path) -> str:
    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(db_file)
    conn.close()
    return f"sqlite:///{db_file}"


def _migrations_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    directory = tmp_path / "migrations"
    directory.mkdir()
    for name, body in files.items():
        (directory / name).write_text(body)
    return directory


def test_applies_pending_migrations_and_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_url = _empty_sqlite_db(tmp_path)
    directory = _migrations_dir(
        tmp_path,
        {"001_widgets.sql": _CREATE_WIDGETS, "002_gadgets.sql": _CREATE_GADGETS},
    )

    run_migrate(_make_args(db=db_url, migrations_dir=str(directory)))

    out = capsys.readouterr().out
    assert "Applied 2 migration(s)" in out
    assert "001_widgets" in out
    assert "002_gadgets" in out

    # The tables actually exist now.
    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(db_file)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert {"widgets", "gadgets"} <= tables


def test_already_up_to_date(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_url = _empty_sqlite_db(tmp_path)
    directory = _migrations_dir(tmp_path, {"001_widgets.sql": _CREATE_WIDGETS})

    # First run applies it; second run is a no-op.
    run_migrate(_make_args(db=db_url, migrations_dir=str(directory)))
    capsys.readouterr()  # discard first-run output

    run_migrate(_make_args(db=db_url, migrations_dir=str(directory)))
    out = capsys.readouterr().out
    assert "Already up to date" in out


def test_broken_migration_fails_loud_exit_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_url = _empty_sqlite_db(tmp_path)
    directory = _migrations_dir(
        tmp_path,
        {"001_broken.sql": "CREATE TABLE oops (this is not valid sql);"},
    )

    with pytest.raises(SystemExit) as exc_info:
        run_migrate(_make_args(db=db_url, migrations_dir=str(directory)))

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Migration failed" in out
    assert "001_broken" in out


def test_missing_migrations_dir_fails_loud_exit_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_url = _empty_sqlite_db(tmp_path)
    missing = tmp_path / "does_not_exist"

    with pytest.raises(SystemExit) as exc_info:
        run_migrate(_make_args(db=db_url, migrations_dir=str(missing)))

    assert exc_info.value.code == 1
    assert "Migration failed" in capsys.readouterr().out


@pytest.mark.issue(380)
def test_issue_380_skip_knob_and_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance: the skip knob skips the on-boot run AND chirp migrate applies + fails loud.

    Criterion 1 — ``CHIRP_SKIP_MIGRATIONS=1`` sets ``AppConfig.skip_migrations``
    via ``from_env()`` (the on-boot gate reads this immutable field; the
    lifecycle gate itself is covered in ``tests/test_app/test_lifespan.py``).

    Criterion 2 — ``chirp migrate`` applies pending migrations and is fail-loud
    (a broken migration exits 1, nothing swallowed).
    """
    # Criterion 1: env parity for the on-boot skip knob.
    for key in list(os.environ):
        if key.startswith("CHIRP_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CHIRP_SKIP_MIGRATIONS", "1")
    assert AppConfig.from_env().skip_migrations is True
    monkeypatch.delenv("CHIRP_SKIP_MIGRATIONS")
    assert AppConfig.from_env().skip_migrations is False

    # Criterion 2a: chirp migrate applies pending migrations.
    db_url = _empty_sqlite_db(tmp_path)
    directory = _migrations_dir(tmp_path, {"001_widgets.sql": _CREATE_WIDGETS})
    run_migrate(_make_args(db=db_url, migrations_dir=str(directory)))
    assert "Applied 1 migration(s)" in capsys.readouterr().out

    # Criterion 2b: chirp migrate fails loud on a broken migration.
    broken_root = tmp_path / "broken"
    broken_root.mkdir()
    broken_db = _empty_sqlite_db(broken_root)
    broken_dir = _migrations_dir(
        broken_root,
        {"001_broken.sql": "CREATE TABLE oops (this is not valid sql);"},
    )
    with pytest.raises(SystemExit) as exc_info:
        run_migrate(_make_args(db=broken_db, migrations_dir=str(broken_dir)))
    assert exc_info.value.code == 1
    assert "Migration failed" in capsys.readouterr().out
