"""Scaffold-default chirp-ui headline checks (issue #157)."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp.cli import _new as new_module
from chirp.cli.templates import PYPROJECT_TOML, V2_APP_CHIRPUI_PY


@pytest.mark.issue(157)
def test_scaffold_pyproject_declares_ui_extra() -> None:
    assert "[project.optional-dependencies]" in PYPROJECT_TOML
    assert 'ui = ["chirp-ui>=0.11.1"]' in PYPROJECT_TOML


@pytest.mark.issue(157)
def test_readme_headlines_chirp_ui_scaffold_default() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "bengal-chirp[ui]" in readme
    assert "chirp new" in readme
    assert "chirpui-*" in readme or "chirp-ui" in readme


@pytest.mark.issue(157)
def test_v2_scaffold_uses_chirp_ui_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(new_module, "_has_chirpui", lambda: True)
    assert "use_chirp_ui" in V2_APP_CHIRPUI_PY
