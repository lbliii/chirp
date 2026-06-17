"""Test isolation for the database-backed pokedex example.

Each test gets its own temporary SQLite database via ``CHIRP_POKEDEX_DB``, so
tests never share or accumulate state and migrations never race across xdist
workers (the shared committed ``pokedex.db`` would otherwise let two concurrent
migration runs collide — "table pokemon already exists" / duplicate seed —
which surfaced as a flake on free-threaded CI). Mirrors the todo example.
"""

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def example_app(tmp_path):
    """Load a fresh App from app.py backed by a per-test temp database."""
    os.environ["CHIRP_POKEDEX_DB"] = str(tmp_path / "pokedex.db")
    try:
        app_path = Path(__file__).parent / "app.py"
        spec = importlib.util.spec_from_file_location("example_pokedex", app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    finally:
        os.environ.pop("CHIRP_POKEDEX_DB", None)
