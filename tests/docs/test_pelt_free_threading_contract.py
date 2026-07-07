"""Drift guards for pelt's free-threading evidence and published driver claims."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE = _ROOT / "docs" / "pelt-free-threading.md"
_CURRENT_DRIVER_DOCS = (
    _ROOT / "site" / "content" / "docs" / "get-started" / "installation.md",
    _ROOT / "site" / "content" / "docs" / "build-apps" / "forms-data" / "database.md",
    _ROOT / "site" / "content" / "docs" / "about" / "architecture.md",
)


@pytest.mark.issue(259)
def test_pelt_evidence_maps_every_concurrency_gate() -> None:
    text = _EVIDENCE.read_text()

    for proof in (
        "test_should_parallelize_requires_threshold_and_nogil",
        "test_parallel_row_decode_overlaps_on_native_threads",
        "test_codec_registry_concurrent_writes_publish_untorn_snapshots",
        "test_pool_checkout_is_exclusive_under_task_contention",
        "test_pool_does_not_republish_connection_until_reset_finishes",
        "test_error_drains_ready_frame_before_rollback_and_reuse",
        "test_pool_rolls_back_failed_transaction_before_reuse",
        "test_parallel_checkouts_keep_statement_caches_single_owner",
    ):
        assert proof in text

    assert "not a throughput claim" in text
    assert "PYTHON_GIL=0" in text


@pytest.mark.issue(259)
def test_current_postgres_docs_name_the_in_tree_pelt_driver() -> None:
    for path in _CURRENT_DRIVER_DOCS:
        text = path.read_text()
        assert "pelt" in text
        assert "asyncpg" not in text

    installation = _CURRENT_DRIVER_DOCS[0].read_text()
    assert "no extra dependency" in installation
