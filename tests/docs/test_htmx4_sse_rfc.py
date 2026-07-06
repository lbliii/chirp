"""Machine-checked decision inventory for RFC 010 (#550)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RFC = ROOT / "docs" / "rfcs" / "010-htmx4-sse-eventstream.md"
SPIKE = ROOT / "tests" / "spikes" / "test_htmx4_sse_preview.py"


@pytest.mark.issue(550)
def test_rfc_010_records_the_complete_htmx4_sse_contract() -> None:
    text = RFC.read_text(encoding="utf-8")

    assert "**Status:** Draft" in text
    assert "4.0.0-beta5" in text
    assert "5300af9e7af8b196f9fbf806cab79a5780b62291" in text
    assert "Unnamed htmx 4 messages are the only automatic HTML swap messages" in text
    assert "Named messages are DOM events only" in text
    assert "<hx-partial>" in text
    assert "data-chirp-signal" in text
    assert "Last-Event-ID" in text
    assert "app-owned cursor recovery remains unchanged" in text
    assert "htmx 2, htmx 4, and generic clients receive explicit dialects" in text
    assert "## Security, cache, proxy, and CSP consequences" in text
    assert "## Free-threading consequences" in text
    assert "## Required implementation proof" in text
    assert "## Approval gate" in text


def test_rfc_010_contains_steward_convergence_and_decision_logs() -> None:
    text = RFC.read_text(encoding="utf-8")

    assert text.count("Steward:") == 6
    for steward in (
        "Rendering",
        "Realtime",
        "Protocol And Negotiation",
        "Contract Checks",
        "Testing Helpers",
        "Narrative Docs",
    ):
        assert f"Steward: {steward}" in text
    assert "promotes it to P0" in text
    assert "The global sweep used for this accepted P0 was" in text
    assert "### Accepted in this draft" in text
    assert "### Deferred to implementation issues" in text
    assert "### Rejected" in text


def test_rfc_010_and_browser_spike_pin_the_same_upstream_assets() -> None:
    rfc = RFC.read_text(encoding="utf-8")
    spike = SPIKE.read_text(encoding="utf-8")

    for value in (
        "5300af9e7af8b196f9fbf806cab79a5780b62291",
        "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68",
        "aa9aa14f10ddbf13a8fc4f8bbd6bc14e0b09b64d668d17e831e69763eac72558",
    ):
        assert value in rfc
        assert value in spike
    assert "CHIRP_HTMX4_SSE_SPIKE" in spike
    assert "@pytest.mark.integration" in spike
