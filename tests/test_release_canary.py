"""Release-policy coverage for the pinned Furatena compatibility canary."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "python-publish.yml"
POLICY = ROOT / "docs" / "release-policy.md"
FURATENA_REVISION = "da584bf9fe19ec1376fdc0b23c7fb1b657b026b8"
CANARY_TESTS = (
    "tests/test_fura_cli_standalone.py::test_init_app_passes_strict_content_check",
    "tests/test_fura_cli_standalone.py::test_author_page_chrome_routes_and_status_model",
    "tests/test_shell_boost_links.py::TestShellBoostHrefs::test_boost_filter_skips_assets",
    "tests/test_chirp_docs_search.py::TestHybridSearchCore::test_hybrid_search_returns_hits",
    "tests/test_chirp_docs_search.py::TestHybridSearchCore::test_build_search_page_cards_groups_by_node",
    "tests/test_chirp_docs_view_lint.py::TestAuthorStaleRoute::test_author_sse_event_reports_invalidation_payload",
    "tests/test_chirp_docs_view_lint.py::TestAuthorStaleRoute::test_author_page_actions_contract_is_stable_for_mobile_and_htmx",
    "tests/test_chirp_docs_view_lint.py::TestAuthorStaleRoute::test_author_reload_after_source_edit_updates_dom_and_clears_hints",
    "tests/test_chirp_docs_maturity.py::TestMaturityPreviewParity::test_preview_theme_mounts_frozen_vendor",
    "tests/test_chirp_docs_static_export.py::TestMiniStaticExport::test_export_writes_html_and_sidecars",
    "tests/test_fura_cli_standalone.py::test_init_app_freezes_and_exports_static_site",
)


@pytest.mark.issue(500)
def test_release_canary_is_pinned_artifact_based_and_advisory() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "furatena-canary:" in workflow
    assert "continue-on-error: true" in workflow
    assert "needs:\n      - release-build" in workflow
    assert "FURATENA_CANARY_TOKEN" in workflow
    assert FURATENA_REVISION in workflow
    assert "uv sync --locked --all-groups" in workflow
    assert "actions/download-artifact" in workflow
    assert "name: release-dists" in workflow
    assert "--force-reinstall" in workflow
    assert "--no-deps" in workflow
    assert "import_path.is_relative_to(environment)" in workflow
    assert "working-directory: furatena" in workflow
    assert all(node_id in workflow for node_id in CANARY_TESTS)
    node_ids = tuple(
        line.strip().removesuffix(" \\")
        for line in workflow.splitlines()
        if line.lstrip().startswith("tests/")
    )
    assert node_ids == CANARY_TESTS


@pytest.mark.issue(500)
def test_release_policy_owns_canary_triage_and_pin_cadence() -> None:
    policy = POLICY.read_text(encoding="utf-8")

    assert "## Furatena Compatibility Canary" in policy
    assert FURATENA_REVISION in policy
    assert "non-blocking" in policy
    assert "FURATENA_CANARY_TOKEN" in policy
    assert "read-only Contents" in policy
    assert "at least quarterly" in policy
    assert "Checkout, missing secret, or revision mismatch" in policy
    assert "Locked dependency installation" in policy
    assert "Wheel installation or provenance assertion" in policy
    assert "Compatibility-test failure" in policy
