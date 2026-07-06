"""Machine-checked decision inventory for RFC 012 (#545)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RFC = ROOT / "docs" / "rfcs" / "012-htmx4-preview-provisioning.md"
SPIKE = ROOT / "tests" / "spikes" / "test_htmx4_preview_provisioning.py"


@pytest.mark.issue(545)
def test_rfc_012_records_the_preview_contract() -> None:
    text = RFC.read_text(encoding="utf-8")
    assert "**Status:** Implemented" in text
    assert 'AppConfig(htmx=True, htmx_version="4.0.0-beta5")' in text
    assert "htmx-2-compat" in text
    assert "hx-sse" in text
    assert "htmx_compatibility category is ERROR" in text
    assert "## Required implementation proof" in text
    assert "approval gate" in text.lower()


def test_rfc_012_records_steward_convergence() -> None:
    text = RFC.read_text(encoding="utf-8")
    assert text.count("Steward:") == 5
    for steward in (
        "App Lifecycle",
        "Server And Negotiation",
        "Contract Checks",
        "CLI And Scaffolds",
        "Narrative Docs",
    ):
        assert f"Steward: {steward}" in text
    assert "converge on mixed delivery as P0" in text
    assert "## Dependencies, risks, minority report, and not-now" in text
    assert "Accepted:" in text
    assert "Rejected:" in text


def test_rfc_and_spike_pin_the_same_assets() -> None:
    rfc = RFC.read_text(encoding="utf-8")
    spike = SPIKE.read_text(encoding="utf-8")
    for value in (
        "5300af9e7af8b196f9fbf806cab79a5780b62291",
        "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68",
        "7d7fe881d6ae6d4e661b0113e8504bb15acfc1dc1970f07db109bb20c432e53d",
        "fcc844a52779d8450c1c4796feea8d038943f908b9ee974322c276230e6c86cc",
    ):
        assert value in rfc
        assert value in spike
    assert "CHIRP_HTMX4_PROVISIONING_SPIKE" in spike
