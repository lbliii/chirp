"""Live-Postgres lifecycle, fencing, and concurrency proof for issue #677."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

import anyio
import pytest

from chirp.data._jobs import (
    ClaimedJob,
    EnqueueResult,
    JobMigrationRequiredError,
    JobProgress,
    JobQueueConfigurationError,
    PostgresJobStore,
    StaleJobClaimError,
    migration_directory,
)
from chirp.data.database import Database

PG_DSN = os.environ.get("CHIRP_TEST_PG_DSN")
requires_pg = pytest.mark.skipif(
    not PG_DSN,
    reason="CHIRP_TEST_PG_DSN not set — durable-job PostgreSQL coverage skipped",
)


@pytest.fixture
async def jobs_db() -> Database:
    assert PG_DSN is not None
    database = Database(PG_DSN, pool_size=12, echo=True)
    await database.connect()
    try:
        exists = await database.fetch_val("SELECT to_regclass('_chirp_job_schema')")
        if exists is None:
            migration = (migration_directory() / "001_durable_jobs.sql").read_text(encoding="utf-8")
            await database.execute_script(migration)
        await database.execute("TRUNCATE TABLE _chirp_jobs")
        await database.execute("DELETE FROM _chirp_job_queues")
        yield database
    finally:
        await database.execute("TRUNCATE TABLE _chirp_jobs")
        await database.execute("DELETE FROM _chirp_job_queues")
        await database.disconnect()


@requires_pg
@pytest.mark.issue(677)
async def test_live_missing_migration_failure_uses_current_transaction_schema(
    jobs_db: Database,
) -> None:
    store = PostgresJobStore(jobs_db)

    async with jobs_db.transaction():
        await jobs_db.execute("SET LOCAL search_path TO pg_temp")
        with pytest.raises(JobMigrationRequiredError, match=r"001_durable_jobs\.sql"):
            await store.check_ready()


@requires_pg
@pytest.mark.issue(677)
async def test_enqueue_round_trip_idempotency_and_null_keys(
    jobs_db: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = PostgresJobStore(jobs_db)
    secret = "payload-must-not-reach-query-logs"
    payload = {"tenant": secret, "items": [1, True, None]}
    caplog.set_level(logging.DEBUG, logger="chirp.data")

    first = await store.enqueue(
        "reports.build",
        payload,
        payload_version=2,
        queue_name="reports",
        queue_limit=2,
        idempotency_key=f"report-42-{secret}",
    )
    duplicate = await store.enqueue(
        "reports.build",
        {"ignored": "because the retained identity wins"},
        payload_version=2,
        queue_name="reports",
        queue_limit=2,
        idempotency_key=f"report-42-{secret}",
    )
    without_key_a = await store.enqueue(
        "reports.build", {}, payload_version=2, queue_name="reports", queue_limit=2
    )
    without_key_b = await store.enqueue(
        "reports.build", {}, payload_version=2, queue_name="reports", queue_limit=2
    )

    assert first.created is True
    assert duplicate == EnqueueResult(job_id=first.job_id, created=False)
    assert without_key_a.job_id != without_key_b.job_id
    snapshot = await store.get(first.job_id)
    assert snapshot is not None
    assert snapshot.payload == payload
    assert snapshot.payload_version == 2
    assert snapshot.state == "pending"
    assert secret not in caplog.text


@requires_pg
@pytest.mark.issue(677)
async def test_concurrent_idempotent_enqueues_retain_one_identity(jobs_db: Database) -> None:
    store = PostgresJobStore(jobs_db)
    results: list[EnqueueResult] = []
    lock = anyio.Lock()

    async def enqueue(index: int) -> None:
        result = await store.enqueue(
            "mail.send",
            {"index": index},
            payload_version=1,
            queue_name="mail",
            queue_limit=8,
            idempotency_key="same-delivery",
        )
        async with lock:
            results.append(result)

    async with anyio.create_task_group() as tasks:
        for index in range(12):
            tasks.start_soon(enqueue, index)

    assert len({result.job_id for result in results}) == 1
    assert sum(result.created for result in results) == 1


@requires_pg
@pytest.mark.issue(677)
async def test_priority_capacity_success_and_terminal_failure(jobs_db: Database) -> None:
    store = PostgresJobStore(jobs_db)
    low = await store.enqueue(
        "work.run", {"rank": "low"}, payload_version=1, queue_name="work", priority=-1
    )
    high = await store.enqueue(
        "work.run", {"rank": "high"}, payload_version=1, queue_name="work", priority=10
    )

    first = await store.claim("work", "worker-a")
    assert first is not None
    assert first.job_id == high.job_id
    assert await store.claim("work", "worker-b") is None

    await store.succeed(first)
    second = await store.claim("work", "worker-b")
    assert second is not None
    assert second.job_id == low.job_id
    await store.fail(second, failure_code="invalid_input", failure_summary="Safe summary")

    succeeded = await store.get(high.job_id)
    failed = await store.get(low.job_id)
    assert succeeded is not None
    assert succeeded.state == "succeeded"
    assert failed is not None
    assert failed.state == "failed"
    assert failed.failure_code == "invalid_input"
    assert failed.failure_summary == "Safe summary"


@requires_pg
@pytest.mark.issue(677)
async def test_concurrent_claimers_never_exceed_capacity_or_share_attempts(
    jobs_db: Database,
) -> None:
    store = PostgresJobStore(jobs_db)
    for index in range(10):
        await store.enqueue(
            "batch.run",
            {"index": index},
            payload_version=1,
            queue_name="batch",
            queue_limit=3,
        )

    claims: list[ClaimedJob] = []
    lock = anyio.Lock()

    async def claim(index: int) -> None:
        result = await store.claim("batch", f"worker-{index}")
        if result is not None:
            async with lock:
                claims.append(result)

    async with anyio.create_task_group() as tasks:
        for index in range(20):
            tasks.start_soon(claim, index)

    assert len(claims) == 3
    assert len({claim.job_id for claim in claims}) == 3
    assert len({claim.lease_token for claim in claims}) == 3


@requires_pg
@pytest.mark.issue(677)
async def test_expired_claim_reclaims_and_rejects_every_stale_owner_operation(
    jobs_db: Database,
) -> None:
    store = PostgresJobStore(jobs_db, lease_seconds=1)
    result = await store.enqueue(
        "leases.run", {}, payload_version=1, queue_name="leases", max_attempts=3
    )
    stale = await store.claim("leases", "worker-old")
    assert stale is not None
    await anyio.sleep(1.1)
    current = await store.claim("leases", "worker-new")
    assert current is not None
    assert current.job_id == result.job_id
    assert current.attempt == 2
    assert current.lease_token != stale.lease_token

    operations = (
        lambda: store.renew(stale),
        lambda: store.update_progress(stale, JobProgress("old", 1, 1)),
        lambda: store.succeed(stale),
        lambda: store.retry(stale, failure_code="retry", failure_summary="retry"),
        lambda: store.fail(stale, failure_code="failed", failure_summary="failed"),
    )
    for operation in operations:
        with pytest.raises(StaleJobClaimError):
            await operation()

    await store.succeed(current)


@requires_pg
@pytest.mark.issue(677)
async def test_progress_is_revisioned_fenced_and_does_not_change_state(jobs_db: Database) -> None:
    store = PostgresJobStore(jobs_db)
    result = await store.enqueue("export.run", {}, payload_version=1, queue_name="exports")
    await store.enqueue("other.run", {}, payload_version=1, queue_name="other")
    claim = await store.claim("exports", "worker-a")
    assert claim is not None

    renewed = await store.renew(claim)
    assert renewed > claim.lease_expires_at
    assert await store.update_progress(claim, JobProgress("starting", 0, 2)) == 1
    assert await store.update_progress(claim, JobProgress("halfway", 1, 2)) == 2
    forged = replace(claim, lease_token=uuid4())
    with pytest.raises(StaleJobClaimError):
        await store.update_progress(forged, JobProgress("forged", 2, 2))
    wrong_queue = replace(claim, queue_name="other")
    with pytest.raises(StaleJobClaimError):
        await store.succeed(wrong_queue)

    snapshot = await store.get(result.job_id)
    assert snapshot is not None
    assert snapshot.state == "running"
    assert snapshot.progress == {"status": "halfway", "step": 1, "total": 2}
    assert snapshot.progress_revision == 2


@requires_pg
@pytest.mark.issue(677)
async def test_retry_uses_database_backoff_and_exhaustion_is_terminal(jobs_db: Database) -> None:
    store = PostgresJobStore(jobs_db)
    result = await store.enqueue(
        "retry.run",
        {},
        payload_version=1,
        queue_name="retries",
        max_attempts=2,
        backoff_base_seconds=1,
        backoff_max_seconds=1,
    )
    first = await store.claim("retries", "worker-a")
    assert first is not None
    retried = await store.retry(first, failure_code="transient", failure_summary="Try again")
    assert retried.state == "pending"
    assert await store.claim("retries", "worker-too-early") is None
    await anyio.sleep(1.1)

    second = await store.claim("retries", "worker-b")
    assert second is not None
    assert second.attempt == 2
    exhausted = await store.retry(
        second,
        failure_code="transient",
        failure_summary="Retry budget exhausted",
    )
    assert exhausted.state == "failed"
    assert await store.claim("retries", "worker-c") is None

    snapshot = await store.get(result.job_id)
    assert snapshot is not None
    assert snapshot.state == "failed"
    assert snapshot.terminal_at is not None


@requires_pg
@pytest.mark.issue(677)
async def test_queue_policy_conflict_fails_without_mutating_capacity(jobs_db: Database) -> None:
    store = PostgresJobStore(jobs_db)
    await store.enqueue("policy.run", {}, payload_version=1, queue_name="policy", queue_limit=2)

    with pytest.raises(JobQueueConfigurationError, match="conflicts"):
        await store.enqueue("policy.run", {}, payload_version=1, queue_name="policy", queue_limit=3)

    row = await jobs_db.fetch_one(
        _QueueLimit,
        "SELECT concurrency_limit FROM _chirp_job_queues WHERE queue_name = $1",
        "policy",
    )
    assert row is not None
    assert row.concurrency_limit == 2


@pytest.mark.issue(677)
def test_live_postgres_module_uses_package_migration_path() -> None:
    assert Path(migration_directory(), "001_durable_jobs.sql").is_file()


@dataclass(frozen=True, slots=True)
class _QueueLimit:
    concurrency_limit: int
