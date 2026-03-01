"""Pytest configuration for the llm_playground example.

Provides ``example_module`` and ``example_app`` fixtures that patch
``use_chirp_ui`` so chirp-ui does not need to be installed to run the
tests, and exposes the loaded module so tests can monkeypatch
``_ollama_models`` and ``LLM`` for mock-based testing.
"""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def example_module(monkeypatch):
    """Load a fresh module with chirp-ui dependency mocked out."""
    import chirp.ext.chirp_ui

    monkeypatch.setattr(
        chirp.ext.chirp_ui, "use_chirp_ui", lambda app, prefix="/static": None
    )

    app_path = Path(__file__).parent / "app.py"
    spec = importlib.util.spec_from_file_location("example_llm_playground", app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def example_app(example_module):
    """Return the App instance from the freshly loaded module."""
    return example_module.app
