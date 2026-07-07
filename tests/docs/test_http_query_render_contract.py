"""Published HTTP QUERY render and DevTools claims stay aligned with #529."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.issue(529)

_ROOT = Path(__file__).parents[2]


def test_query_rfc_records_render_surface_receipt() -> None:
    rfc = (_ROOT / "docs" / "rfcs" / "009-http-query.md").read_text()
    assert "Executable rendering and diagnostics receipt (#529)" in rfc
    assert "classifies `QUERY` as safe rather than" in rfc
    assert "This receipt did not modify `templating/render_plan.py`" in rfc


def test_query_user_docs_keep_one_typed_render_pipeline() -> None:
    routes = (
        _ROOT / "site" / "content" / "docs" / "build-apps" / "pages-navigation" / "routes.md"
    ).read_text()
    devtools = (_ROOT / "docs" / "devtools.md").read_text()
    assert "QUERY uses the same typed HTML return pipeline" in routes
    assert "reports QUERY as a safe method" in routes
    assert "method semantics, timing phases, response content type" in devtools


def test_query_browser_proof_stays_in_ci() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "tests/contracts/test_query_devtools_browser.py" in workflow
