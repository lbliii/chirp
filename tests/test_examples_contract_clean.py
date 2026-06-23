"""Every shipped example must pass the hypermedia contract check with zero
ERROR-severity issues.

Examples are teaching material: a broken hypermedia contract in an example
teaches the wrong pattern and ``chirp dev``/``app.run()`` would refuse to start
on it. The per-example ``test_app.py`` files assert *behavior*; only a handful
historically asserted *contract cleanliness*, which let SSE-scope and
function-middleware ERRORs drift into shipped examples while their behavior
tests stayed green.

This test closes that gap uniformly — it discovers every ``examples/**/app.py``
and fails if any produces an ERROR-severity contract issue, so a new example
cannot silently ship with a broken contract.
"""

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest

from chirp.contracts import check_hypermedia_surface
from tests.helpers.shape_registry import isolated_shape_registry

_EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples"
_APP_FILES = sorted(_EXAMPLES_ROOT.rglob("app.py"))
_IDS = [str(p.parent.relative_to(_EXAMPLES_ROOT)) for p in _APP_FILES]


@pytest.fixture(autouse=True)
def _isolate_shape_registry():
    """Restore the process-global ``@shape`` registry around each example load.

    An ``@shape`` example registers Shapes by name; loading many examples — and
    the same example across this file and ``test_examples_smoke.py`` — in one
    process would otherwise collide on duplicate names. Snapshot/restore mirrors
    the module-purge isolation this file already performs.
    """
    with isolated_shape_registry():
        yield


def _load_isolated(app_path: Path):
    """Load an example's ``app`` with sys.modules/sys.path isolation.

    Examples ship local helper modules imported as top-level names (``store``,
    ``models``, …). Loading many examples in one process would otherwise let
    the first example's ``store`` shadow every later one. We snapshot module
    state, then purge anything newly imported from under ``examples/`` so each
    example loads against a clean slate.
    """
    examples_root = str(_EXAMPLES_ROOT)
    # Drop any example-local module left cached by an earlier test/example so a
    # different example's identically-named ``store``/``models`` can't shadow
    # this one (Python caches modules by name, not by path).
    for name in [
        n
        for n, mod in list(sys.modules.items())
        if (f := getattr(mod, "__file__", None)) and f.startswith(examples_root)
    ]:
        sys.modules.pop(name, None)

    before_modules = set(sys.modules)
    before_path = sys.path[:]
    sys.path.insert(0, str(app_path.parent))
    spec = importlib.util.spec_from_file_location(
        f"example_contract_{app_path.parent.name}", app_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            spec.loader.exec_module(module)
        return getattr(module, "app", None)
    finally:
        sys.path[:] = before_path
        for name in set(sys.modules) - before_modules:
            mod = sys.modules.get(name)
            mod_file = getattr(mod, "__file__", None)
            if name == spec.name or (mod_file and mod_file.startswith(examples_root)):
                sys.modules.pop(name, None)


@pytest.mark.parametrize("app_path", _APP_FILES, ids=_IDS)
def test_example_has_no_contract_errors(app_path: Path) -> None:
    app = _load_isolated(app_path)
    assert app is not None, f"{app_path} defines no top-level `app`"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = check_hypermedia_surface(app)
    errors = [i for i in result.issues if getattr(i.severity, "name", "") == "ERROR"]
    assert not errors, "{} has contract ERROR(s):\n{}".format(
        app_path.parent.relative_to(_EXAMPLES_ROOT),
        "\n".join(f"  [{i.category}] {i.message}" for i in errors),
    )


@pytest.mark.parametrize("app_path", _APP_FILES, ids=_IDS)
def test_example_has_no_template_stream_shape_warnings(app_path: Path) -> None:
    app = _load_isolated(app_path)
    assert app is not None, f"{app_path} defines no top-level `app`"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = check_hypermedia_surface(app)
    warnings = [
        i
        for i in result.issues
        if i.category == "template_stream_client_shape"
        and getattr(i.severity, "name", "") == "WARNING"
    ]
    assert not warnings, "{} has template_stream_client_shape WARNING(s):\n{}".format(
        app_path.parent.relative_to(_EXAMPLES_ROOT),
        "\n".join(f"  {i.message}" for i in warnings),
    )


def test_discovered_all_examples() -> None:
    """Guard against the glob silently matching nothing (e.g. a moved dir)."""
    assert len(_APP_FILES) >= 40
