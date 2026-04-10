"""Test isolation for the reactive tasks example."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def example_app():
    """Load a fresh App from app.py with a clean store."""
    app_path = Path(__file__).parent / "app.py"
    spec = importlib.util.spec_from_file_location("example_reactive_tasks", app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
