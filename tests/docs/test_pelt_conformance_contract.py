"""Drift guards for Pelt's live/sans-I/O conformance map (#260)."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CONFORMANCE = _ROOT / "docs" / "pelt-conformance.md"
_LIVE_TESTS = _ROOT / "tests" / "test_pelt" / "test_connection_integration.py"


@pytest.mark.issue(260)
def test_pelt_conformance_map_names_live_proofs_and_open_boundaries() -> None:
    conformance = _CONFORMANCE.read_text()
    live_tests = _LIVE_TESTS.read_text()

    for proof in (
        "test_parallel_checkouts_keep_statement_caches_single_owner",
        "test_live_leaf_codec_matrix",
        "test_live_array_and_range_types_preserve_text_when_binary_is_not_requested",
        "test_database_executemany_and_stream",
        "test_database_fetch_execute_transaction",
        "test_pool_rolls_back_failed_transaction_before_reuse",
    ):
        assert proof in conformance
        assert f"def {proof}" in live_tests

    assert "Missing live lifecycle proof" in conformance
    assert "live binary-result negotiation remains open" in conformance
    assert "Missing live server-assigned OID proof" in conformance
    assert "INTERVAL" in conformance
