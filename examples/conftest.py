"""Shared pytest configuration for chirp examples.

Provides the ``example_app`` fixture that loads a fresh App instance
from the ``app.py`` file in the same directory as the test.  Each call
re-executes app.py in an isolated module namespace, so every test starts
with clean state (e.g. the todo list is empty).
"""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def example_app(request: pytest.FixtureRequest):
    """Load a fresh App from the sibling app.py next to the test file."""
    app_path = Path(request.path).parent / "app.py"
    module_name = f"example_{app_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app
