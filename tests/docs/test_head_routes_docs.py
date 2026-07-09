"""Documentation and dependency contract for first-class HEAD (#554)."""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROUTES_DOC = ROOT / "site" / "content" / "docs" / "build-apps" / "pages-navigation" / "routes.md"


@pytest.mark.issue(554)
def test_routes_document_head_fallback_and_wire_semantics() -> None:
    text = ROUTES_DOC.read_text(encoding="utf-8")
    assert "Every `GET` route also answers `HEAD`" in text
    assert 'request.method == "HEAD"' in text
    assert "zero body bytes" in text
    assert "explicit `HEAD` route" in text
    assert "both `GET` and `HEAD`" in text
    assert "`/health` and" in text
    assert "Before Chirp 0.4.0" in text
    assert "relied on that rejection" in text


@pytest.mark.issue(554)
def test_pounce_dependency_requires_head_fix_release() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pounce = next(dep for dep in project["dependencies"] if dep.startswith("bengal-pounce"))
    assert pounce == "bengal-pounce>=0.9.0"
