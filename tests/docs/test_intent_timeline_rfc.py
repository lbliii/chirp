"""Source-backed status and safety checks for Intent Timeline RFC #336."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "020-intent-timeline.md"


@pytest.mark.issue(336, 647)
def test_intent_timeline_rfc_records_private_capture_implementation_scope() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Accepted; private capture foundation implemented by #647" in text
    assert "**Shipping impact:** Private debug/test capture only" in text
    assert "does not add an `AppConfig` field" in text
    assert "No changelog: #647 changes private debug/test capture internals only" in text


@pytest.mark.issue(336)
def test_intent_timeline_rfc_cites_current_trace_evidence() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/templating/trace.py",
        "src/chirp/server/transition_trace.py",
        "src/chirp/server/debug_runtime.py",
        "src/chirp/server/intent_timeline.py",
        "src/chirp/server/devtools/js/state.js",
        "src/chirp/server/devtools/js/errors.js",
        "src/chirp/server/devtools/js/ui.js",
        "src/chirp/testing/transitions.py",
        "tests/test_transition_trace.py",
        "docs/rfcs/007-sse-last-event-id-recovery.md",
    ):
        assert path in text


@pytest.mark.issue(336)
def test_intent_timeline_rfc_preserves_replay_and_privacy_boundaries() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Observation replay**" in text
    assert "**Execution replay**" in text
    assert "fixture driver" in text
    assert "Chirp must never infer “safe to repeat” from HTTP method alone" in text
    assert "route patterns, never dynamic path parameter values" in text
    assert "request/response bodies and rendered HTML" in text
    assert "debug/test-only" in text
    assert "not a durable business event log" in text


@pytest.mark.issue(336)
def test_intent_timeline_rfc_requires_ordering_and_fail_loud_proof() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "holding the publication lock" in text
    assert "tie-breaker." in text
    assert "truncated=true" in text
    assert "empty target, missing non-optional OOB block" in text
    assert "A 10-step htmx flow with one OOB response" in text
    assert "requires a separate review" in text
