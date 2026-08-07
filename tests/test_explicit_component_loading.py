"""Explicit component loading — no ambient chirp-ui discovery (#860)."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.config import AppConfig as Config
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity
from chirp.templating.filters import BUILTIN_FILTERS
from chirp.templating.integration import create_environment

_INTEGRATION = (
    Path(__file__).resolve().parents[1] / "src" / "chirp" / "templating" / "integration.py"
)
_EXT_CHIRP_UI = Path(__file__).resolve().parents[1] / "src" / "chirp" / "ext" / "chirp_ui.py"


def _module_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".", 1)[0])
    return names


@pytest.mark.issue(860)
def test_core_templating_has_no_module_scope_chirp_ui_import() -> None:
    """Import-closure: ambient chirp-ui must not live at module scope in core."""
    assert "chirp_ui" not in _module_level_imports(_INTEGRATION)
    # Explicit bridge may import at function scope only (lazy).
    tree = ast.parse(_EXT_CHIRP_UI.read_text(encoding="utf-8"), filename=str(_EXT_CHIRP_UI))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "use_chirp_ui":
            fn_imports = {
                alias.name.split(".", 1)[0]
                for stmt in node.body
                if isinstance(stmt, ast.Import)
                for alias in stmt.names
            } | {
                stmt.module.split(".", 1)[0]
                for stmt in node.body
                if isinstance(stmt, ast.ImportFrom) and stmt.module
            }
            assert "chirp_ui" in fn_imports
            break
    else:
        pytest.fail("use_chirp_ui not found")


@pytest.mark.issue(860)
def test_create_environment_does_not_import_chirp_ui(tmp_path: Path) -> None:
    """Calling create_environment must not pull chirp_ui into sys.modules."""
    had_chirp_ui = "chirp_ui" in sys.modules
    chirp_ui_mod = sys.modules.pop("chirp_ui", None)
    # Also drop submodules so a partial reload cannot sneak in.
    stale = [name for name in sys.modules if name == "chirp_ui" or name.startswith("chirp_ui.")]
    for name in stale:
        sys.modules.pop(name, None)
    try:
        before = set(sys.modules)
        env = create_environment(Config(template_dir=str(tmp_path)), filters={}, globals_={})
        after = set(sys.modules) - before
        assert not any(name == "chirp_ui" or name.startswith("chirp_ui.") for name in after)
        assert "chirpui_asset_path" not in env.globals
    finally:
        if chirp_ui_mod is not None:
            sys.modules["chirp_ui"] = chirp_ui_mod
        elif had_chirp_ui:
            importlib.import_module("chirp_ui")


@pytest.mark.issue(860)
def test_present_but_unused_chirp_ui_does_not_load_package_templates(
    tmp_path: Path,
) -> None:
    """Installed chirp-ui without use_chirp_ui must not expose chirpui/ templates."""
    from kida.exceptions import TemplateNotFoundError

    pytest.importorskip("chirp_ui")
    env = create_environment(Config(template_dir=str(tmp_path)), filters={}, globals_={})
    with pytest.raises(TemplateNotFoundError, match=r"chirpui/card\.html"):
        env.get_template("chirpui/card.html")
    assert env.filters["html_attrs"] is BUILTIN_FILTERS["html_attrs"]
    assert "chirpui_asset_path" not in env.globals


@pytest.mark.issue(860)
def test_explicit_use_chirp_ui_registers_package_templates(tmp_path: Path) -> None:
    """use_chirp_ui is the documented compatibility path that activates chirp-ui."""
    pytest.importorskip("chirp_ui")
    from chirp.ext.chirp_ui import use_chirp_ui

    (tmp_path / "page.html").write_text("<p>ok</p>", encoding="utf-8")
    app = App(AppConfig(template_dir=str(tmp_path), skip_contract_checks=True))
    use_chirp_ui(app)
    app.freeze()
    env = app._runtime_state.kida_env
    assert env is not None
    template = env.get_template("chirpui/card.html")
    assert template is not None
    assert "chirpui_asset_path" in env.globals
    assert env.filters["html_attrs"] is not BUILTIN_FILTERS["html_attrs"]
    assert getattr(env.filters["html_attrs"], "__module__", "").startswith("chirp_ui")


@pytest.mark.issue(860)
def test_chirpui_runtime_diagnostic_for_stale_implicit_assumption(tmp_path: Path) -> None:
    """Templates importing chirpui/ without use_chirp_ui get an actionable diagnostic."""
    (tmp_path / "page.html").write_text(
        '{% from "chirpui/card.html" import card %}<html>{{ card() }}</html>',
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=str(tmp_path), skip_contract_checks=True))

    @app.route("/")
    def index():
        return "ok"

    result = check_hypermedia_surface(app)
    runtime_issues = [i for i in result.issues if i.category == "chirpui_runtime"]
    assert len(runtime_issues) == 1
    assert runtime_issues[0].severity == Severity.INFO
    assert "use_chirp_ui(app)" in runtime_issues[0].message
    assert "package presence alone" in runtime_issues[0].message


@pytest.mark.issue(860)
def test_identical_config_env_shape_with_and_without_chirp_ui_importable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same AppConfig + empty plugin_loaders → same env regardless of chirp-ui presence."""
    config = Config(template_dir=str(tmp_path))

    def _env_fingerprint() -> tuple[object, ...]:
        env = create_environment(config, filters={}, globals_={})
        filter_names = tuple(sorted(env.filters.keys()))
        global_names = tuple(sorted(env.globals.keys()))
        loader = env.loader
        loader_types = tuple(type(part).__name__ for part in getattr(loader, "loaders", (loader,)))
        return filter_names, global_names, loader_types

    with_ui = _env_fingerprint()

    # Simulate chirp-ui absent for a second fingerprint without ambient side effects.
    real_import = importlib.import_module

    def _block_chirp_ui(name: str, *args: object, **kwargs: object):
        if name == "chirp_ui" or name.startswith("chirp_ui."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _block_chirp_ui)
    # create_environment no longer imports chirp_ui; fingerprint must match.
    without_ui = _env_fingerprint()
    assert with_ui == without_ui
