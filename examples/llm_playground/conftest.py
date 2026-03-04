"""Pytest configuration for the llm_playground example.

Provides ``example_module`` and ``example_app`` fixtures and exposes the
loaded module so tests can monkeypatch ``_ollama_models`` and ``LLM`` for
mock-based testing.
"""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def example_module(monkeypatch):
    """Load a fresh module for each test.

    This example imports ChirpUI templates/macros that require ChirpUI's
    runtime registration (filters/globals). If chirp-ui isn't installed,
    skip example tests cleanly.
    """
    try:
        import chirp_ui  # noqa: F401
    except ImportError:
        pytest.skip("llm_playground requires chirp-ui to render templates")

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
