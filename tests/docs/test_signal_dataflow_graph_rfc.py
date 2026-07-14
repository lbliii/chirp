"""Source-backed status checks for signal-dataflow RFC #343."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "018-signal-dataflow-graph.md"


@pytest.mark.issue(343)
def test_signal_graph_rfc_records_private_phase_one_without_public_shipping() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Phase 1 implemented (private compiler model)" in text
    assert "Implemented by #683" in text
    assert "does not add it" in text
    assert "current `signal_orphan` result" in text
    assert "No changelog: the Phase 1 compiler model is private" in text


@pytest.mark.issue(343)
def test_signal_graph_rfc_cites_current_split_graph_evidence() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/realtime/signals.py",
        "src/chirp/contracts/rules_signals.py",
        "src/chirp/pages/reactive/index.py",
        "src/chirp/contracts/rules_reactive.py",
        "src/chirp/app/hypermedia_program.py",
    ):
        assert path in text
    assert "10 registered names" in text
    assert "five derived nodes" in text
    assert "273 templates" in text
    assert "lobby_snapshot" in text


@pytest.mark.issue(343)
def test_signal_graph_rfc_preserves_contract_and_security_gates() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "retain `signal_dead_binding` `ERROR`" in text
    assert "separate implementation review" in text
    assert "session audience keys or payload" in text
    assert "explicit design check-in before implementation" in text
