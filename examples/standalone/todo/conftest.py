"""Test isolation for the database-backed todo example.

Each test gets its own temporary SQLite database via ``CHIRP_TODO_DB``,
so tests never share or accumulate state and no files are left behind.
"""

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def example_app(tmp_path):
    """Load a fresh App from app.py backed by a per-test temp database."""
    os.environ["CHIRP_TODO_DB"] = str(tmp_path / "todo.db")
    try:
        app_path = Path(__file__).parent / "app.py"
        spec = importlib.util.spec_from_file_location("example_todo", app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    finally:
        os.environ.pop("CHIRP_TODO_DB", None)
