"""Source-backed status checks for durable-job RFC #615."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "022-durable-job-model.md"


@pytest.mark.issue(615, 677)
def test_durable_job_rfc_records_private_phase_one_shipping_boundary() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Accepted — Phase 1 private store implemented" in text
    assert "**Shipping impact:** Private data surface only" in text
    assert "It does not add a public API" in text
    assert "change any `app.check()` output" in text
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


@pytest.mark.issue(615, 677)
def test_durable_job_rfc_records_phase_one_decisions_and_defers_later_surfaces() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "## Open questions requiring later maintainer check-in" in text
    assert "### Phase 1 implementation decisions" in text
    assert "_chirp_job_schema" in text
    assert "locked queue row" in text
    assert "64 KiB encoded limit" in text
    assert "not approved public API" in text
    assert "What future `app.check()` categories" in text
    assert "durable-job semantics depend on a particular Milo revision" in text
    assert "status` / `step` / `total" in text
