"""Drift guards for Pelt's live/sans-I/O conformance map (#260, #695)."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CONFORMANCE = _ROOT / "docs" / "pelt-conformance.md"
_LIVE_TESTS = _ROOT / "tests" / "test_pelt" / "test_connection_integration.py"


@pytest.mark.issue(260, 695)
def test_pelt_conformance_map_names_live_proofs_and_open_boundaries() -> None:
    conformance = _CONFORMANCE.read_text()
    prose = " ".join(conformance.split())
    live_tests = _LIVE_TESTS.read_text()

    for proof in (
        "test_parallel_checkouts_keep_statement_caches_single_owner",
        "test_live_leaf_codec_matrix",
        "test_live_array_and_range_types_preserve_text_when_binary_is_not_requested",
        "test_live_extended_query_negotiates_dynamic_types_and_text_fallback",
        "test_live_binary_interval_is_independent_of_interval_style",
        "test_database_executemany_and_stream",
        "test_database_fetch_execute_transaction",
        "test_pool_rolls_back_failed_transaction_before_reuse",
        "test_listen_notify_delivery_unsubscribe_and_close",
    ):
        assert proof in conformance
        assert f"def {proof}" in live_tests

    assert "exactly one socket reader" in conformance
    assert "Missing live lifecycle proof" not in conformance
    assert "live binary-result negotiation remains open" not in conformance
    assert "Missing live server-assigned OID proof" not in conformance
    assert "one explicit format code per result column" in conformance
    assert "Unknown base, domain, pseudo, and multirange types remain faithful text" in prose
    assert "statement-level `Describe` always reports format zero" in prose
