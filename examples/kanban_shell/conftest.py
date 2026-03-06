"""Conftest for kanban_shell — ensures store module can be imported when loading app."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def example_app(request: pytest.FixtureRequest):
    """Load app from app.py with kanban_shell directory on path for store import."""
    here = Path(request.path).parent
    app_path = here / "app.py"
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    try:
        module_name = f"example_{here.name}"
        spec = importlib.util.spec_from_file_location(module_name, app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    finally:
        if str(here) in sys.path:
            sys.path.remove(str(here))
