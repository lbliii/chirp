"""Machine-checked decision inventory for RFC 011 (#549)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RFC = ROOT / "docs" / "rfcs" / "011-htmx4-trigger-timing.md"
SPIKE = ROOT / "tests" / "spikes" / "test_htmx4_trigger_headers_preview.py"


@pytest.mark.issue(549)
def test_rfc_011_records_the_trigger_timing_decision() -> None:
    text = RFC.read_text(encoding="utf-8")

    assert "**Status:** Implemented for the explicit preview lane" in text
    assert "fail loudly with migration guidance" in text
    assert "### 4. Reject a compatibility adapter" in text
    assert "htmx:before:settle" in text
    assert "htmx:after:settle" in text
    assert "assert_hx_trigger" in text
    assert "HX-Request-Type" in text
    assert "## Required implementation proof" in text
    assert "## Approval gate" in text


def test_rfc_011_contains_steward_convergence_and_decision_logs() -> None:
    text = RFC.read_text(encoding="utf-8")

    assert text.count("Steward:") == 5
    for steward in (
        "HTTP Primitives",
        "Server And Negotiation",
        "Contract Checks",
        "Testing Helpers",
        "Narrative Docs",
    ):
        assert f"Steward: {steward}" in text
    assert "Convergence Rule keeps it at P0" in text
    assert "The global sweep for this accepted P0 was" in text
    assert "### Accepted in this draft" in text
    assert "### Deferred to implementation" in text
    assert "### Rejected" in text


def test_rfc_011_and_browser_spike_pin_the_same_upstream_assets() -> None:
    rfc = RFC.read_text(encoding="utf-8")
    spike = SPIKE.read_text(encoding="utf-8")

    for value in (
        "bdc7d7d3e25d0390c7ee11049806e8279b075598",
        "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de",
        "5300af9e7af8b196f9fbf806cab79a5780b62291",
        "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68",
    ):
        assert value in spike
    for commit in (
        "bdc7d7d3e25d0390c7ee11049806e8279b075598",
        "5300af9e7af8b196f9fbf806cab79a5780b62291",
    ):
        assert commit in rfc
    assert "CHIRP_HTMX4_TRIGGER_SPIKE" in spike
    assert "@pytest.mark.integration" in spike
