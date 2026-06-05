"""Shared pytest configuration for chirp examples.

Provides the ``example_app`` fixture that loads a fresh App instance
from the ``app.py`` file in the same directory as the test.  Each call
re-executes app.py in an isolated module namespace, so every test starts
with clean state (e.g. the todo list is empty).
"""

import contextlib
import importlib.util
import sys
from pathlib import Path

import pytest

# Ensure project root is on path so tests.helpers is importable
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_EXAMPLES_ROOT = str(Path(__file__).resolve().parent)


def _purge_example_modules() -> None:
    """Drop any cached module loaded from under ``examples/``.

    Examples ship local helper modules imported as top-level names (``store``,
    ``models``, page ``_viewmodel`` modules, …). Python caches modules by name,
    so one example's ``store`` would otherwise shadow every other example's
    ``store`` — and a test file that does ``from store import …`` at module
    level caches it at *collection* time, before any fixture runs. Purging both
    before and after each load keeps every example self-contained.
    """
    for name, mod in list(sys.modules.items()):
        mod_file = getattr(mod, "__file__", None)
        if mod_file and mod_file.startswith(_EXAMPLES_ROOT):
            sys.modules.pop(name, None)


@pytest.fixture
def example_app(request: pytest.FixtureRequest):
    """Load a fresh App from the sibling app.py next to the test file.

    The example dir goes first on ``sys.path`` for the load, and example-local
    modules are purged before and after so each example resolves its own
    helpers against a clean slate (see :func:`_purge_example_modules`).
    """
    app_dir = Path(request.path).parent
    app_path = app_dir / "app.py"
    module_name = f"example_{app_dir.name}"

    _purge_example_modules()
    sys.path.insert(0, str(app_dir))
    spec = importlib.util.spec_from_file_location(module_name, app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        yield module.app
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(str(app_dir))
        sys.modules.pop(module_name, None)
        _purge_example_modules()
