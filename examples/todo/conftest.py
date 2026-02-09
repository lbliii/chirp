"""Test isolation for the database-backed todo example.

Each test needs a fresh, empty database. This fixture deletes the
SQLite file before and after each test so migrations re-create the
schema from scratch via TestClient's lifespan handling.
"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_todo_db():
    db_file = Path(__file__).parent / "todo.db"
    db_file.unlink(missing_ok=True)
    yield
    db_file.unlink(missing_ok=True)
