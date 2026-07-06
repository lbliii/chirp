"""Machine-checked decision inventory for RFC 013 (#548)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RFC = ROOT / "docs" / "rfcs" / "013-htmx4-default-contracts.md"
SPIKE = ROOT / "tests" / "spikes" / "test_htmx4_default_contracts.py"


@pytest.mark.issue(548)
def test_rfc_013_records_all_default_decisions() -> None:
    text = RFC.read_text(encoding="utf-8")
    for value in (
        "Inheritance",
        "4xx errors",
        "5xx errors",
        "OOB order",
        "DELETE data",
        "History",
        "Queue",
        "Timeout",
    ):
        assert f"| {value} |" in text
    assert "noSwap to 204, 304, and 5xx" in text
    assert "hx-sync" in text
    assert "60000" in text
    assert "## Required implementation proof" in text
    assert "approval gate" in text.lower()


def test_rfc_013_records_governance_and_convergence() -> None:
    text = RFC.read_text(encoding="utf-8")
    assert text.count("Steward:") == 4
    assert text.count("Verification Status:\nmachine-verified") == 4
    assert "converge on broad-target error safety as P0" in text
    assert "## Dependencies, risks, minority report, and not-now" in text
    assert "Accepted in this draft:" in text
    assert "Rejected:" in text


def test_rfc_and_spike_pin_the_same_preview() -> None:
    rfc = RFC.read_text(encoding="utf-8")
    spike = SPIKE.read_text(encoding="utf-8")
    for value in (
        "5300af9e7af8b196f9fbf806cab79a5780b62291",
        "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68",
        "7d7fe881d6ae6d4e661b0113e8504bb15acfc1dc1970f07db109bb20c432e53d",
    ):
        assert value in spike
    assert "5300af9e7af8b196f9fbf806cab79a5780b62291" in rfc
    assert "CHIRP_HTMX4_DEFAULTS_SPIKE" in spike
