"""Drift guards for pelt's free-threading evidence and published driver claims."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE = _ROOT / "docs" / "pelt-free-threading.md"
_CI_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_CURRENT_DRIVER_DOCS = (
    _ROOT / "site" / "content" / "docs" / "get-started" / "installation.md",
    _ROOT / "site" / "content" / "docs" / "build-apps" / "forms-data" / "database.md",
    _ROOT / "site" / "content" / "docs" / "about" / "architecture.md",
)


@pytest.mark.issue(259, 695)
def test_pelt_evidence_maps_every_concurrency_gate() -> None:
    text = _EVIDENCE.read_text()

    for proof in (
        "test_should_parallelize_requires_threshold_and_nogil",
        "test_parallel_row_decode_overlaps_on_native_threads",
        "test_codec_registry_concurrent_writes_publish_untorn_snapshots",
        "test_dynamic_codec_registries_are_connection_local",
        "test_pool_checkout_is_exclusive_under_task_contention",
        "test_suspense_shaped_pool_checkout_stress_stays_exclusive_and_idle",
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


@pytest.mark.issue(260)
def test_live_postgres_ci_covers_13_through_18() -> None:
    workflow = _CI_WORKFLOW.read_text()
    evidence = _EVIDENCE.read_text()

    for image in (
        "postgres:13.22-bookworm",
        "postgres:14",
        "postgres:15",
        "postgres:16",
        "postgres:17",
        "postgres:18",
    ):
        assert f"image: {image}" in workflow

    assert "fail-fast: false" in workflow
    assert "PostgreSQL 13" in evidence
    assert "majors 14" in evidence
    assert "final 13.22 image" in evidence
    assert "compatibility lane" in evidence


@pytest.mark.issue(260, 695)
def test_data_pg_docs_publish_driver_and_performance_boundaries() -> None:
    database = _CURRENT_DRIVER_DOCS[1].read_text()
    evidence = _EVIDENCE.read_text()

    for text in (database, evidence):
        assert "pure Python" in text
        assert "libpq" in text

    assert "do not import `chirp.data.drivers._pelt`" in database
    assert "`db.stream()` owns one pooled connection" in database
    assert "`db.execute_many()` is currently a convenience loop" in database
    assert "server-assigned enum, array, range, and composite OIDs" in database
    assert "unexpected unknown binary data fails" in database
    assert "does not scale with pool size" in evidence
