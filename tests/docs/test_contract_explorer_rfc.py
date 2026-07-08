"""Source-backed status and safety checks for Contract Explorer RFC #337."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "021-contract-explorer.md"


@pytest.mark.issue(337)
def test_contract_explorer_rfc_is_explicitly_non_shipping() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Proposed" in text
    assert "**Shipping impact:** None" in text
    assert "does not add a CLI flag" in text
    assert "No changelog: proposed RFC only" in text


@pytest.mark.issue(337)
def test_contract_explorer_rfc_cites_current_authorities() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/app/hypermedia_program.py",
        "src/chirp/app/hypermedia_program_compiler.py",
        "src/chirp/cli/_check.py",
        "src/chirp/contracts/serialize.py",
        "src/chirp/cli/_routes.py",
        "src/chirp/server/transition_trace.py",
        "src/chirp/testing/transitions.py",
        "src/chirp/testing/route_smoke.py",
        "src/chirp/server/route_explorer.py",
        "tests/test_route_explorer.py",
        "docs/devtools.md",
    ):
        assert path in text


@pytest.mark.issue(337)
def test_contract_explorer_rfc_separates_static_findings_and_evidence() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "What is declared or inferred?" in text
    assert "What is statically wrong or uncertain?" in text
    assert "What was behaviorally exercised?" in text
    assert "not automatically a failure" in text
    assert "Browser-only behavior" in text
    assert "cannot suppress an `app.check()` error" in text


@pytest.mark.issue(337)
def test_contract_explorer_rfc_rejects_unsafe_execution_and_public_drift() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "No automatic route fuzzing" in text
    assert "never infer that GET/HEAD is side-effect-free" in text
    assert "must not join a message to a node using substring matching" in text
    assert "agents scrape" in text
    assert "Production-default apps expose no" in text
    assert "Explorer route" in text
    assert "No route executes during app freeze" in text
    assert "requires its own compatibility and severity review" in text
