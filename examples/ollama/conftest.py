"""Pytest configuration for the ollama example.

Overrides the shared ``example_app`` fixture to also expose the loaded
module, so tests can monkeypatch ``ollama_chat`` for mock tests.
"""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def example_module(request: pytest.FixtureRequest):
    """Load a fresh module from app.py (includes the ``app`` and ``ollama_chat``)."""
    app_path = Path(request.path).parent / "app.py"
    spec = importlib.util.spec_from_file_location("example_ollama", app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def example_app(example_module):
    """Return the App instance from the freshly loaded module."""
    return example_module.app
