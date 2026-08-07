"""Scaffold-default chirp-ui checks (issues #157 / #860)."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp.cli import main
from chirp.cli.templates import PYPROJECT_TOML, V2_APP_CHIRPUI_PY, V2_APP_PY


@pytest.mark.issue(157)
def test_scaffold_pyproject_declares_ui_extra() -> None:
    assert "[project.optional-dependencies]" in PYPROJECT_TOML
    assert 'ui = ["chirp-ui>=0.11.4"]' in PYPROJECT_TOML


@pytest.mark.issue(157)
def test_readme_headlines_chirp_ui_scaffold_default() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "bengal-chirp[ui]" in readme
    assert "chirp new" in readme
    assert "chirpui-*" in readme or "chirp-ui" in readme


@pytest.mark.issue(860)
def test_default_scaffold_ignores_installed_chirpui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installed chirp-ui must not change default ``chirp new`` output."""
    from chirp.cli import _new as new_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(new_module, "_has_chirpui", lambda: True)
    main(["new", "myapp"])
    app = (tmp_path / "myapp" / "app.py").read_text(encoding="utf-8")
    assert "use_chirp_ui" not in app
    assert app == V2_APP_PY


@pytest.mark.issue(860)
def test_with_chirpui_flag_emits_explicit_compatibility_scaffold() -> None:
    """``--with-chirpui`` remains the documented explicit compatibility path."""
    assert "use_chirp_ui" in V2_APP_CHIRPUI_PY
