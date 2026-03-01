"""Pytest configuration for the rag_demo example.

Patches ``use_chirp_ui`` (requires optional chirp-ui package) to a no-op
and configures a temporary SQLite database via ``DB_URL`` so each test
starts with a clean schema and sample documents.  Also exposes
``example_module`` for tests that need to monkeypatch module-level names
such as ``llm`` and ``_db_var``.
"""

import importlib.util
from pathlib import Path

import pytest

# Skip entire module when patitas lacks render_llm/sanitize (patitas>=0.3.2)
try:
    from patitas import render_llm, sanitize  # noqa: F401
    from patitas.sanitize import llm_safe  # noqa: F401
except ImportError:
    pytest.skip(
        "rag_demo requires patitas>=0.3.2 (render_llm, sanitize)",
        allow_module_level=True,
    )


@pytest.fixture
def example_module(monkeypatch, tmp_path):
    """Load a fresh module with external dependencies mocked."""
    import chirp.ext.chirp_ui

    monkeypatch.setattr(chirp.ext.chirp_ui, "use_chirp_ui", lambda app, prefix="/static": None)

    db_file = tmp_path / "rag_test.db"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_file}")
    # Skip remote doc sync — fall back to sample docs only ("," = empty URL list)
    monkeypatch.setenv("RAG_DOC_SOURCES", ",")

    app_path = Path(__file__).parent / "app.py"
    spec = importlib.util.spec_from_file_location("example_rag_demo", app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def example_app(example_module):
    """Return the App instance from the freshly loaded module."""
    return example_module.app
