"""Source-backed status checks for durable-job RFC #615."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "022-durable-job-model.md"


@pytest.mark.issue(615)
def test_durable_job_rfc_is_explicitly_non_shipping() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Proposed" in text
    assert "**Shipping impact:** None" in text
    assert "This RFC does not add or" in text
    assert "change any `app.check()` output" in text
    assert "No changelog, public API, site, example, scaffold, CLI, migration" in text


@pytest.mark.issue(615)
def test_durable_job_rfc_cites_current_foundations_without_claiming_a_job_runtime() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/data/database.py",
        "src/chirp/data/migrate.py",
        "src/chirp/app/lifecycle.py",
        "ContractCheckSnapshot",
    ):
        assert path in text
    assert "There is no `JobStore`" in text
    assert "does not persist, claim, retry, lease, or execute work" in text


@pytest.mark.issue(615)
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


@pytest.mark.issue(615)
def test_durable_job_rfc_defers_stop_and_ask_surfaces() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "## Open questions requiring maintainer check-in" in text
    assert "provisional module, registration form, enqueue form" in text
    assert "What exact SQL tables, column types, indexes" in text
    assert "What future `app.check()` categories" in text
    assert "durable-job semantics depend on a particular Milo revision" in text
    assert "This RFC does not decide whether all three fields are required" in text
