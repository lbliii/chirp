"""Test isolation for the database-backed dashboard_live example.

Each test gets its own temporary SQLite database via ``CHIRP_DASHBOARD_DB``,
so seed data from one test never bleeds into another.
"""

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def example_app(tmp_path):
    """Load a fresh App from app.py backed by a per-test temp database."""
    os.environ["CHIRP_DASHBOARD_DB"] = str(tmp_path / "dashboard.db")
    try:
        app_path = Path(__file__).parent / "app.py"
        spec = importlib.util.spec_from_file_location("example_dashboard_live", app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    finally:
        os.environ.pop("CHIRP_DASHBOARD_DB", None)
