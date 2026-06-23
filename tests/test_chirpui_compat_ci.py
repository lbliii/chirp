"""Release-gate wiring for chirp-ui cross-version CI (issue #157)."""

from __future__ import annotations

from pathlib import Path

import pytest

_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


@pytest.mark.issue(157)
def test_ci_declares_chirp_ui_compat_matrix() -> None:
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "chirp-ui-compat:" in text
    assert "chirp-ui-version" in text
    assert "tests/test_chirpui_boundary.py" in text
