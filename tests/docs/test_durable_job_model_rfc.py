"""Source-backed status checks for durable-job RFC #615 and decision #719."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "022-durable-job-model.md"


@pytest.mark.issue(615, 677, 719)
def test_durable_job_rfc_records_private_store_and_decision_boundary() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Accepted — Phase 1 implemented; Phase 2/3 boundaries approved" in text
    assert "**Shipping impact:** Private data surface plus an approved decision record" in text
    assert "Neither issue adds a public API" in text
    assert "This RFC itself does not add or change any" in text
    assert "`app.check()` output" in text
    assert "No site example, scaffold, CLI" in text


@pytest.mark.issue(615, 677)
def test_durable_job_rfc_cites_private_store_without_claiming_an_executor() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/data/database.py",
        "src/chirp/data/migrate.py",
        "src/chirp/app/lifecycle.py",
        "ContractCheckSnapshot",
    ):
        assert path in text
    assert "src/chirp/data/_jobs.py" in text
    assert "There is still no public job definition, handler registry, claim loop" in text
    assert "does not persist, claim, retry, lease, or execute work" in text


@pytest.mark.issue(615, 677)
def test_durable_job_rfc_preserves_delivery_and_schema_boundaries() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for phrase in (
        "explicit at-least-once semantics",
        "`FOR UPDATE SKIP LOCKED`",
        "owner plus opaque lease-token fencing",
        "queue-scoped idempotency",
        "advisory JSON-safe progress",
        "reviewable migrations rather than automatic schema mutation",
        "There is no `cancelled` state",
    ):
        assert phrase in text


@pytest.mark.issue(615, 677, 719)
def test_durable_job_rfc_records_approved_and_deferred_surfaces() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "## Approved Phase 2 and Phase 3 boundaries" in text
    assert "## Deferred decisions requiring later maintainer check-in" in text
    assert "### Phase 1 implementation decisions" in text
    assert "_chirp_job_schema" in text
    assert "locked queue row" in text
    assert "64 KiB encoded limit" in text
    assert "not approved public API" in text
    assert "provisional `jobs` contract category" in text
    assert "exactly one executor per app instance" in text
    assert "Payload compatibility is exact and fail-loud" in text
    assert "SQLite parity is rejected for epic #615" in text
    assert "status` / `step` / `total" in text


@pytest.mark.issue(719)
def test_durable_job_rfc_assigns_decision_proof_and_collateral() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "### Decision matrix and proof ownership" in text
    for concern in (
        "| Crash recovery |",
        "| Idempotency |",
        "| Retries |",
        "| Malformed definitions |",
        "| Lifecycle and free-threading |",
        "| Optional dependencies |",
        "| SQLite gaps |",
        "| Migration ownership |",
    ):
        assert concern in text
    assert "#720 for validated enqueue wiring" in text
    assert "Phase 3 native child" in text
    assert "Acceptance #719 is" in text
    assert "n/a (decision-only RFC and parent-scope reconciliation)" in text
