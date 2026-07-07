"""Compatibility and browser-lane locks for issue #576."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.issue(576)

_ROOT = Path(__file__).resolve().parents[2]


def test_browser_dependency_and_ci_lane_pin_chrome_149() -> None:
    project = _ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8")
    workflow = _ROOT.joinpath(".github/workflows/ci.yml").read_text(encoding="utf-8")
    smoke = _ROOT.joinpath("examples/standalone/webmcp_form/test_browser_smoke.py").read_text(
        encoding="utf-8"
    )

    assert '"playwright==1.61.0"' in project
    assert "webmcp_form/test_browser_smoke.py" in workflow
    assert '"149.0.7827.55"' in smoke


def test_compatibility_docs_are_explicit_about_preview_and_fallback() -> None:
    docs = _ROOT.joinpath("docs/forms-production.md").read_text(encoding="utf-8")

    for required in (
        "Chrome 149",
        "chrome://flags/#enable-webmcp-testing",
        "Permissions-Policy: tools=()",
        "0b676d27a08aafd3b4f8a709756eeeab342fd9bd",
        "visible browsing context",
        "agentInvoked",
        "respondWith()",
        "does not support those changed surfaces",
        "all POST/PUT/PATCH/DELETE projections omit `toolautosubmit`",
    ):
        assert required in docs
