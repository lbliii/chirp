"""Source-backed status checks for enhancement-tier RFC #347."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "016-enhancement-tier-contracts.md"


@pytest.mark.issue(347)
def test_enhancement_tier_rfc_records_the_compiler_increment_boundary() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Accepted in part" in text
    assert "requires `kida-templates>=0.12.0`" in text
    assert "No severity changes in this compiler increment" in text
    assert "A changelog fragment records the dependency and authoring impact" in text


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

    assert "separate implementation check-ins" in text
    assert "No private Kida parser import or source-regex compatibility shim" in text
    assert "runtime must never substitute an empty block" in text


@pytest.mark.issue(723)
def test_enhancement_tier_rfc_records_the_evidence_decisions() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for decision in (
        "`fallback_declared` is false",
        "Edge is preserved with `resolved=False`",
        "**No-go now**",
        "**Revise**",
        "no implicit ChirpUI defaults",
        "explicit severity check-in",
    ):
        assert decision in text
