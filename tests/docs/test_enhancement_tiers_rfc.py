"""Source-backed status checks for enhancement-tier RFC #347."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "016-enhancement-tier-contracts.md"


@pytest.mark.issue(347)
def test_enhancement_tier_rfc_is_explicitly_non_shipping() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Proposed" in text
    assert "not valid Kida 0.11 syntax" in text
    assert "No severity changes in this RFC" in text
    assert "No changelog: proposed RFC only" in text


@pytest.mark.issue(347)
def test_enhancement_tier_rfc_cites_current_proof_surfaces() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/contracts/rules_nojs_floor.py",
        "tests/contracts/test_nojs_floor.py",
        "examples/standalone/nojs_floor/",
        "src/chirp/app/hypermedia_program.py",
        "examples/standalone/webmcp_form/test_browser_smoke.py",
    ):
        assert path in text


@pytest.mark.issue(347)
def test_enhancement_tier_rfc_preserves_constitutional_gates() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "separate Chirp implementation check-in" in text
    assert "No private Kida parser import or source-regex compatibility shim" in text
    assert "runtime must never substitute an empty block" in text
