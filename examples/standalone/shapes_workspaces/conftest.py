"""Test isolation for the Shapes workspaces example.

Each test gets its own temporary SQLite database via ``CHIRP_WORKSPACES_DB`` and
a freshly loaded ``app`` (so migrations + seed run from scratch). The autouse
``@shape`` registry isolation lives in ``examples/conftest.py`` and applies here
too, so reloading ``app.py`` per test does not collide on Shape names.
"""

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def example_module(tmp_path):
    """Load a fresh example module backed by a per-test temp database.

    Returns the module so tests can reach the Shape classes (``Project``,
    ``Dashboard``, …) for data-layer assertions, not just ``app``.
    """
    os.environ["CHIRP_WORKSPACES_DB"] = str(tmp_path / "workspaces.db")
    try:
        app_path = Path(__file__).parent / "app.py"
        spec = importlib.util.spec_from_file_location("example_shapes_workspaces", app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        os.environ.pop("CHIRP_WORKSPACES_DB", None)


@pytest.fixture
def example_app(example_module):
    """The loaded App (backed by a per-test temp database)."""
    return example_module.app
