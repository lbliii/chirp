"""Machine-checked evidence map for the canonical full-application journey."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from examples.inventory import load_inventory, validate_inventory  # noqa: E402

JOURNEY = ROOT / "site/content/docs/tutorials/full-application-journey.md"
FURATENA_CANARY_REVISION = "da584bf9fe19ec1376fdc0b23c7fb1b657b026b8"

REQUIRED_CAPABILITIES = {
    "standalone/todo": {
        "csrf",
        "data",
        "forms",
        "fragments",
        "mutations",
        "no-js",
        "security",
    },
    "chirpui/kanban_shell": {"app-shell", "csrf", "forms", "fragments", "oob", "sse"},
    "standalone/dashboard_live": {"data", "fragments", "sse", "suspense"},
    "chirpui/lucky_cat": {
        "app-shell",
        "csrf",
        "data",
        "forms",
        "mutations",
        "oob",
        "sse",
        "suspense",
    },
    "standalone/freeze_site": {"freeze", "pages"},
}

BEHAVIOR_PROOFS = {
    "examples/standalone/todo/test_app.py": {
        "test_index_full_page",
        "test_index_fragment",
        "test_plain_add_redirects_after_persisting",
    },
    "examples/chirpui/kanban_shell/test_app.py": {
        "test_index_boosted_fragment_keeps_page_content_contract",
        "test_add_returns_oob",
        "test_sse_includes_oob_swaps",
    },
    "examples/standalone/dashboard_live/test_app.py": {
        "test_index_has_seeded_data",
        "test_receives_events",
    },
    "examples/chirpui/lucky_cat/test_app.py": {
        "test_app_check_passes",
        "test_plain_post_redirects",
        "test_deferred_panels_swap_to_existing_dom_ids",
    },
    "examples/standalone/freeze_site/test_app.py": {
        "test_home_page_renders_with_layout",
    },
}

CONTRACT_PROOFS = {
    "tests/test_testing_helpers.py": {
        "test_boosted_full_document_failure_names_target_and_shape",
    },
    "tests/contracts/test_oob_pipeline_e2e.py": {
        "test_oob_with_missing_block_fails_loud_pr90",
    },
    "tests/contracts/test_forms.py": {
        "test_mutating_form_without_token_warns_when_csrf_middleware_active",
    },
}


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    }


@pytest.mark.issue(512)
def test_full_application_journey_has_executable_inventory_backing() -> None:
    entries = load_inventory()
    validate_inventory(entries)
    by_path = {entry.path: entry for entry in entries}
    text = JOURNEY.read_text(encoding="utf-8")

    for example, required in REQUIRED_CAPABILITIES.items():
        assert example in by_path
        assert required <= set(by_path[example].capabilities)
        assert f"examples/{example}" in text

    for relative_path, expected_tests in BEHAVIOR_PROOFS.items():
        path = ROOT / relative_path
        assert path.is_file()
        assert expected_tests <= _test_functions(path)


def test_contract_drills_remain_tied_to_precise_regression_proofs() -> None:
    text = JOURNEY.read_text(encoding="utf-8")
    assert "Full document in a boosted target" in text
    assert "Missing OOB block" in text
    assert "Mutating form without CSRF state" in text

    for relative_path, expected_tests in CONTRACT_PROOFS.items():
        path = ROOT / relative_path
        assert path.is_file()
        assert expected_tests <= _test_functions(path)


def test_journey_links_to_pinned_furatena_canary_evidence() -> None:
    text = JOURNEY.read_text(encoding="utf-8")

    assert "https://github.com/lbliii/chirp/pull/556" in text
    assert "https://github.com/lbliii/chirp/issues/500" in text
    assert FURATENA_CANARY_REVISION in text
    assert "built Chirp wheel" in text
    assert "Furatena lockfile" in text
