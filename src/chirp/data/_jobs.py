"""Private Postgres durable-job store.

This Phase 1 module deliberately has no public re-export, app lifecycle wiring,
handler registry, or executor. PostgreSQL owns every lifecycle transition; the
Python object holds only an immutable database reference and lease duration.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from chirp.data._mapping import map_row
from chirp.data.database import Database, _execute_fetch_one, _execute_statement
from chirp.data.errors import DataError, QueryError

type JSONValue = bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None
type JobState = Literal["pending", "running", "succeeded", "failed"]

_SCHEMA_VERSION = 1
_MAX_PAYLOAD_BYTES = 65_536
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 10_000
_MAX_PROGRESS_STATUS_BYTES = 512
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
_FAILURE_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

_MIGRATION_MESSAGE = (
    "Durable job schema is missing. Apply the checked-in "
    "src/chirp/data/migrations/jobs/001_durable_jobs.sql migration through the normal "
    "`chirp migrate` workflow before using the private Postgres job store."
)


class JobStoreError(DataError):
    """Base error for the private provisional job store."""


class JobMigrationRequiredError(JobStoreError):
    """Raised when the reviewed durable-job migration has not been applied."""


class JobSchemaVersionError(JobStoreError):
    """Raised when the database job schema is not the version this store expects."""


class JobValidationError(JobStoreError):
    """Raised before invalid or unbounded durable data reaches PostgreSQL."""


class JobQueueConfigurationError(JobStoreError):
    """Raised when callers disagree about one queue's persisted capacity."""


class StaleJobClaimError(JobStoreError):
    """Raised when an owner/token pair no longer owns an active lease."""


class _JobQueryError(QueryError):
    """Redacted database failure retaining only SQLSTATE for internal routing."""

    __slots__ = ("sqlstate",)

    def __init__(self, message: str, *, sqlstate: str | None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    """Private enqueue result distinguishing insertion from idempotent reuse."""

    job_id: UUID
    created: bool


@dataclass(frozen=True, slots=True)
class JobProgress:
    """Bounded advisory progress persisted under the active lease fence."""

    status: str
    step: int = 0
    total: int = 0


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """Immutable attempt snapshot and the opaque fence needed to settle it."""

    job_id: UUID
    definition_name: str
    payload: JSONValue
    payload_version: int
    queue_name: str
    priority: int
    attempt: int
    max_attempts: int
    owner_id: str
    lease_token: UUID
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class RetryResult:
    """State and database-derived availability after a retryable failure."""

    state: JobState
    available_at: datetime


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """Private read model for tests and future operator projections."""

    job_id: UUID
    definition_name: str
    payload: JSONValue
    payload_version: int
    queue_name: str
    priority: int
    idempotency_key: str | None
    max_attempts: int
    state: JobState
    attempts: int
    available_at: datetime
    owner_id: str | None
    lease_token: UUID | None
    lease_expires_at: datetime | None
    progress: JSONValue | None
    progress_revision: int
    failure_code: str | None
    failure_summary: str | None
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


@dataclass(frozen=True, slots=True)
class _SchemaRow:
    version: int


@dataclass(frozen=True, slots=True)
class _QueueRow:
    concurrency_limit: int
    active_claims: int


@dataclass(frozen=True, slots=True)
class _JobIdRow:
    job_id: UUID


@dataclass(frozen=True, slots=True)
class _LeaseRow:
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class _ProgressRow:
    progress_revision: int


@dataclass(frozen=True, slots=True)
class _RetryRow:
    state: JobState
    available_at: datetime


def migration_directory() -> Path:
    """Return the package-shipped migration directory for private tooling/tests."""
    return Path(__file__).with_name("migrations") / "jobs"


class PostgresJobStore:
    """Private Phase 1 durable store; no handler or poller starts here."""

    __slots__ = ("_db", "_lease_seconds")

    def __init__(self, database: Database, /, *, lease_seconds: int = 30) -> None:
        if database._driver != "postgresql":
            msg = "The private durable job store requires a PostgreSQL Database."
            raise JobStoreError(msg)
        _bounded_int("lease_seconds", lease_seconds, minimum=1, maximum=3600)
        self._db = database
        self._lease_seconds = lease_seconds

    async def check_ready(self) -> None:
        """Fail loud when the reviewed schema migration is absent or incompatible."""
        try:
            row = await self._fetch_one(
                _SchemaRow,
                "SELECT version FROM _chirp_job_schema WHERE singleton = true",
            )
        except _JobQueryError as exc:
            if exc.sqlstate == "42P01":
                raise JobMigrationRequiredError(_MIGRATION_MESSAGE) from None
            raise
        if row is None:
            raise JobMigrationRequiredError(_MIGRATION_MESSAGE)
        if row.version != _SCHEMA_VERSION:
            msg = (
                "Durable job schema version is incompatible: "
                f"expected {_SCHEMA_VERSION}, found {row.version}. Apply the reviewed "
                "durable-job migrations before starting workers."
            )
            raise JobSchemaVersionError(msg)

    async def enqueue(
        self,
        definition_name: str,
        payload: object,
        /,
        *,
        payload_version: int,
        queue_name: str = "default",
        queue_limit: int = 1,
        priority: int = 0,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: int = 1,
        backoff_max_seconds: int = 300,
        delay_seconds: int = 0,
    ) -> EnqueueResult:
        """Persist one JSON-safe job, resolving queue-scoped idempotency atomically."""
        definition_name = _bounded_name("definition_name", definition_name, maximum=200)
        queue_name = _bounded_name("queue_name", queue_name, maximum=128)
        _bounded_int("payload_version", payload_version, minimum=1, maximum=2_147_483_647)
        _bounded_int("queue_limit", queue_limit, minimum=1, maximum=1024)
        _bounded_int("priority", priority, minimum=-1000, maximum=1000)
        _bounded_int("max_attempts", max_attempts, minimum=1, maximum=100)
        _bounded_int("backoff_base_seconds", backoff_base_seconds, minimum=0, maximum=3600)
        _bounded_int("backoff_max_seconds", backoff_max_seconds, minimum=0, maximum=86_400)
        if backoff_max_seconds < backoff_base_seconds:
            msg = "backoff_max_seconds must be greater than or equal to backoff_base_seconds"
            raise JobValidationError(msg)
        _bounded_int("delay_seconds", delay_seconds, minimum=0, maximum=604_800)
        if idempotency_key is not None:
            idempotency_key = _bounded_text("idempotency_key", idempotency_key, maximum=256)
        canonical_payload = _canonical_json(
            payload,
            field_name="payload",
            maximum_bytes=_MAX_PAYLOAD_BYTES,
        )
        job_id = uuid4()

        await self.check_ready()
        async with self._db.transaction():
            await self._execute(
                """
                INSERT INTO _chirp_job_queues (queue_name, concurrency_limit)
                VALUES ($1, $2)
                ON CONFLICT (queue_name) DO NOTHING
                """,
                queue_name,
                queue_limit,
            )
            queue = await self._lock_queue(queue_name)
            if queue.concurrency_limit != queue_limit:
                msg = (
                    "queue_limit conflicts with the capacity already persisted for this queue; "
                    "use one reviewed queue policy across all producers"
                )
                raise JobQueueConfigurationError(msg)

            inserted = await self._fetch_one(
                _JobIdRow,
                """
                INSERT INTO _chirp_jobs (
                    id, definition_name, payload, payload_version, queue_name, priority,
                    idempotency_key, max_attempts, backoff_base_seconds,
                    backoff_max_seconds, available_at
                )
                VALUES (
                    $1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10,
                    clock_timestamp() + ($11::double precision * interval '1 second')
                )
                ON CONFLICT (queue_name, idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                    DO NOTHING
                RETURNING id AS job_id
                """,
                job_id,
                definition_name,
                canonical_payload,
                payload_version,
                queue_name,
                priority,
                idempotency_key,
                max_attempts,
                backoff_base_seconds,
                backoff_max_seconds,
                delay_seconds,
            )
            if inserted is not None:
                return EnqueueResult(job_id=inserted.job_id, created=True)

            existing = await self._fetch_one(
                _JobIdRow,
                """
                SELECT id AS job_id
                FROM _chirp_jobs
                WHERE queue_name = $1 AND idempotency_key = $2
                """,
                queue_name,
                idempotency_key,
            )
            if existing is None:  # pragma: no cover - database uniqueness invariant
                msg = "idempotent enqueue did not retain a job identity"
                raise JobStoreError(msg)
            return EnqueueResult(job_id=existing.job_id, created=False)

    async def claim(self, queue_name: str, owner_id: str, /) -> ClaimedJob | None:
        """Atomically claim one eligible job while holding the queue capacity fence."""
        queue_name = _bounded_name("queue_name", queue_name, maximum=128)
        owner_id = _bounded_name("owner_id", owner_id, maximum=200)
        lease_token = uuid4()
        await self.check_ready()

        async with self._db.transaction():
            queue = await self._reconcile_queue(queue_name)
            await self._execute(
                """
                UPDATE _chirp_jobs
                SET state = 'failed', owner_id = NULL, lease_token = NULL,
                    lease_expires_at = NULL, heartbeat_at = NULL,
                    failure_code = 'attempts_exhausted',
                    failure_summary = 'The maximum attempt count was exhausted.',
                    terminal_at = clock_timestamp(), updated_at = clock_timestamp()
                WHERE queue_name = $1 AND state = 'running'
                    AND lease_expires_at <= clock_timestamp()
                    AND attempts >= max_attempts
                """,
                queue_name,
            )
            if queue.active_claims >= queue.concurrency_limit:
                return None

            claimed = await self._fetch_one(
                ClaimedJob,
                """
                WITH candidate AS (
                    SELECT id
                    FROM _chirp_jobs
                    WHERE queue_name = $1
                        AND attempts < max_attempts
                        AND (
                            (state = 'pending' AND available_at <= clock_timestamp())
                            OR
                            (state = 'running' AND lease_expires_at <= clock_timestamp())
                        )
                    ORDER BY priority DESC, available_at, created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE _chirp_jobs AS job
                SET state = 'running', attempts = job.attempts + 1,
                    owner_id = $2, lease_token = $3,
                    lease_expires_at = clock_timestamp()
                        + ($4::double precision * interval '1 second'),
                    heartbeat_at = clock_timestamp(), updated_at = clock_timestamp(),
                    terminal_at = NULL
                FROM candidate
                WHERE job.id = candidate.id
                RETURNING job.id AS job_id, job.definition_name, job.payload,
                    job.payload_version, job.queue_name, job.priority,
                    job.attempts AS attempt, job.max_attempts, job.owner_id,
                    job.lease_token, job.lease_expires_at
                """,
                queue_name,
                owner_id,
                lease_token,
                self._lease_seconds,
            )
            if claimed is None:
                return None
            await self._execute(
                """
                UPDATE _chirp_job_queues
                SET active_claims = active_claims + 1, updated_at = clock_timestamp()
                WHERE queue_name = $1
                """,
                queue_name,
            )
            return claimed

    async def renew(self, claim: ClaimedJob, /) -> datetime:
        """Extend an unexpired lease, rejecting every stale owner/token pair."""
        row = await self._fetch_one(
            _LeaseRow,
            """
            UPDATE _chirp_jobs
            SET lease_expires_at = clock_timestamp()
                    + ($4::double precision * interval '1 second'),
                heartbeat_at = clock_timestamp(), updated_at = clock_timestamp()
            WHERE id = $1 AND state = 'running' AND owner_id = $2 AND lease_token = $3
                AND lease_expires_at > clock_timestamp()
            RETURNING lease_expires_at
            """,
            claim.job_id,
            claim.owner_id,
            claim.lease_token,
            self._lease_seconds,
        )
        if row is None:
            raise StaleJobClaimError(_stale_claim_message())
        return row.lease_expires_at

    async def update_progress(self, claim: ClaimedJob, progress: JobProgress, /) -> int:
        """Replace advisory progress and increment its revision under the lease fence."""
        status = _bounded_text(
            "progress.status",
            progress.status,
            maximum=_MAX_PROGRESS_STATUS_BYTES,
            byte_limit=True,
        )
        _bounded_int("progress.step", progress.step, minimum=0, maximum=2_147_483_647)
        _bounded_int("progress.total", progress.total, minimum=0, maximum=2_147_483_647)
        if progress.total and progress.step > progress.total:
            msg = "progress.step must not exceed progress.total when total is non-zero"
            raise JobValidationError(msg)
        document = _canonical_json(
            {"status": status, "step": progress.step, "total": progress.total},
            field_name="progress",
            maximum_bytes=2048,
        )
        row = await self._fetch_one(
            _ProgressRow,
            """
            UPDATE _chirp_jobs
            SET progress = $4::jsonb, progress_revision = progress_revision + 1,
                updated_at = clock_timestamp()
            WHERE id = $1 AND state = 'running' AND owner_id = $2 AND lease_token = $3
                AND lease_expires_at > clock_timestamp()
            RETURNING progress_revision
            """,
            claim.job_id,
            claim.owner_id,
            claim.lease_token,
            document,
        )
        if row is None:
            raise StaleJobClaimError(_stale_claim_message())
        return row.progress_revision

    async def succeed(self, claim: ClaimedJob, /) -> None:
        """Fence and record terminal success."""
        await self._settle(
            claim,
            """
            UPDATE _chirp_jobs
            SET state = 'succeeded', owner_id = NULL, lease_token = NULL,
                lease_expires_at = NULL, heartbeat_at = NULL,
                failure_code = NULL, failure_summary = NULL,
                terminal_at = clock_timestamp(), updated_at = clock_timestamp()
            WHERE id = $1 AND state = 'running' AND owner_id = $2 AND lease_token = $3
                AND queue_name = $4
                AND lease_expires_at > clock_timestamp()
            RETURNING id AS job_id
            """,
        )

    async def retry(
        self,
        claim: ClaimedJob,
        /,
        *,
        failure_code: str,
        failure_summary: str,
    ) -> RetryResult:
        """Fence a retry, using snapshotted exponential backoff and database time."""
        failure_code = _validate_failure_code(failure_code)
        failure_summary = _bounded_text("failure_summary", failure_summary, maximum=512)
        await self.check_ready()
        async with self._db.transaction():
            await self._lock_queue(claim.queue_name)
            row = await self._fetch_one(
                _RetryRow,
                """
                UPDATE _chirp_jobs
                SET state = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'pending' END,
                    available_at = CASE
                        WHEN attempts >= max_attempts THEN available_at
                        ELSE clock_timestamp() + (
                            LEAST(
                                backoff_max_seconds::double precision,
                                backoff_base_seconds::double precision
                                    * power(2::double precision, LEAST(attempts - 1, 30))
                            ) * interval '1 second'
                        )
                    END,
                    owner_id = NULL, lease_token = NULL, lease_expires_at = NULL,
                    heartbeat_at = NULL, failure_code = $5, failure_summary = $6,
                    terminal_at = CASE
                        WHEN attempts >= max_attempts THEN clock_timestamp() ELSE NULL
                    END,
                    updated_at = clock_timestamp()
                WHERE id = $1 AND state = 'running' AND owner_id = $2 AND lease_token = $3
                    AND queue_name = $4
                    AND lease_expires_at > clock_timestamp()
                RETURNING state, available_at
                """,
                claim.job_id,
                claim.owner_id,
                claim.lease_token,
                claim.queue_name,
                failure_code,
                failure_summary,
            )
            if row is None:
                raise StaleJobClaimError(_stale_claim_message())
            await self._release_capacity(claim.queue_name)
            return RetryResult(state=row.state, available_at=row.available_at)

    async def fail(
        self,
        claim: ClaimedJob,
        /,
        *,
        failure_code: str,
        failure_summary: str,
    ) -> None:
        """Fence and retain a terminal failed record without traceback or payload copies."""
        failure_code = _validate_failure_code(failure_code)
        failure_summary = _bounded_text("failure_summary", failure_summary, maximum=512)
        await self._settle(
            claim,
            """
            UPDATE _chirp_jobs
            SET state = 'failed', owner_id = NULL, lease_token = NULL,
                lease_expires_at = NULL, heartbeat_at = NULL,
                failure_code = $5, failure_summary = $6,
                terminal_at = clock_timestamp(), updated_at = clock_timestamp()
            WHERE id = $1 AND state = 'running' AND owner_id = $2 AND lease_token = $3
                AND queue_name = $4
                AND lease_expires_at > clock_timestamp()
            RETURNING id AS job_id
            """,
            failure_code,
            failure_summary,
        )

    async def get(self, job_id: UUID, /) -> JobSnapshot | None:
        """Read one retained job without exposing an HTTP or JSON endpoint."""
        await self.check_ready()
        return await self._fetch_one(
            JobSnapshot,
            """
            SELECT id AS job_id, definition_name, payload, payload_version, queue_name,
                priority, idempotency_key, max_attempts, state, attempts, available_at,
                owner_id, lease_token, lease_expires_at, progress, progress_revision,
                failure_code, failure_summary, created_at, updated_at, terminal_at
            FROM _chirp_jobs
            WHERE id = $1
            """,
            job_id,
        )

    async def _settle(self, claim: ClaimedJob, sql: str, *params: str) -> None:
        await self.check_ready()
        async with self._db.transaction():
            await self._lock_queue(claim.queue_name)
            row = await self._fetch_one(
                _JobIdRow,
                sql,
                claim.job_id,
                claim.owner_id,
                claim.lease_token,
                claim.queue_name,
                *params,
            )
            if row is None:
                raise StaleJobClaimError(_stale_claim_message())
            await self._release_capacity(claim.queue_name)

    async def _lock_queue(self, queue_name: str) -> _QueueRow:
        queue = await self._fetch_one(
            _QueueRow,
            """
            SELECT concurrency_limit, active_claims
            FROM _chirp_job_queues
            WHERE queue_name = $1
            FOR UPDATE
            """,
            queue_name,
        )
        if queue is None:
            msg = "The requested queue has no persisted capacity policy; enqueue a job first."
            raise JobQueueConfigurationError(msg)
        return queue

    async def _reconcile_queue(self, queue_name: str) -> _QueueRow:
        await self._lock_queue(queue_name)
        queue = await self._fetch_one(
            _QueueRow,
            """
            UPDATE _chirp_job_queues AS queue
            SET active_claims = (
                    SELECT count(*)::smallint
                    FROM _chirp_jobs AS job
                    WHERE job.queue_name = queue.queue_name AND job.state = 'running'
                        AND job.lease_expires_at > clock_timestamp()
                ),
                updated_at = clock_timestamp()
            WHERE queue.queue_name = $1
            RETURNING queue.concurrency_limit, queue.active_claims
            """,
            queue_name,
        )
        if queue is None:  # pragma: no cover - held row lock prevents deletion
            msg = "The queue capacity row disappeared while its lock was held."
            raise JobStoreError(msg)
        return queue

    async def _release_capacity(self, queue_name: str) -> None:
        await self._execute(
            """
            UPDATE _chirp_job_queues
            SET active_claims = GREATEST(active_claims - 1, 0),
                updated_at = clock_timestamp()
            WHERE queue_name = $1
            """,
            queue_name,
        )

    async def _fetch_one[T](
        self,
        cls: type[T],
        sql: str,
        /,
        *params: Any,
    ) -> T | None:
        """Execute fixed store SQL without echoing bound durable values."""
        async with self._db._connection(write=True) as connection:
            try:
                row = await _execute_fetch_one("postgresql", connection, sql, params)
            except Exception as exc:
                msg = "Durable job database operation failed; bound values were redacted."
                raise _JobQueryError(
                    msg,
                    sqlstate=getattr(exc, "sqlstate", None),
                ) from None
        return None if row is None else map_row(cls, row)

    async def _execute(self, sql: str, /, *params: Any) -> int:
        """Execute fixed store SQL without echoing bound durable values."""
        async with self._db._connection(write=True) as connection:
            try:
                return await _execute_statement("postgresql", connection, sql, params)
            except Exception as exc:
                msg = "Durable job database operation failed; bound values were redacted."
                raise _JobQueryError(
                    msg,
                    sqlstate=getattr(exc, "sqlstate", None),
                ) from None


def _bounded_name(field_name: str, value: object, *, maximum: int) -> str:
    value = _bounded_text(field_name, value, maximum=maximum)
    if _NAME_RE.fullmatch(value) is None:
        msg = f"{field_name} must use only letters, digits, '.', '_', ':', '/', or '-'"
        raise JobValidationError(msg)
    return value


def _bounded_text(
    field_name: str,
    value: object,
    *,
    maximum: int,
    byte_limit: bool = False,
) -> str:
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise JobValidationError(msg)
    size = len(value.encode("utf-8")) if byte_limit else len(value)
    if size > maximum:
        unit = "UTF-8 bytes" if byte_limit else "characters"
        msg = f"{field_name} must be at most {maximum} {unit}"
        raise JobValidationError(msg)
    return value


def _bounded_int(field_name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be an integer"
        raise JobValidationError(msg)
    if not minimum <= value <= maximum:
        msg = f"{field_name} must be between {minimum} and {maximum}"
        raise JobValidationError(msg)
    return value


def _validate_failure_code(value: object) -> str:
    value = _bounded_text("failure_code", value, maximum=64)
    if _FAILURE_CODE_RE.fullmatch(value) is None:
        msg = "failure_code must use lowercase letters, digits, '.', '_', or '-'"
        raise JobValidationError(msg)
    return value


def _canonical_json(value: object, *, field_name: str, maximum_bytes: int) -> str:
    nodes = 0

    def validate(item: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            msg = f"{field_name} contains too many JSON values"
            raise JobValidationError(msg)
        if depth > _MAX_JSON_DEPTH:
            msg = f"{field_name} exceeds the maximum JSON nesting depth"
            raise JobValidationError(msg)
        if item is None or isinstance(item, (bool, str)):
            return
        if isinstance(item, int):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                msg = f"{field_name} contains a non-finite number"
                raise JobValidationError(msg)
            return
        if isinstance(item, list):
            for child in item:
                validate(child, depth + 1)
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    msg = f"{field_name} object keys must be strings"
                    raise JobValidationError(msg)
                validate(child, depth + 1)
            return
        msg = f"{field_name} must contain only canonical JSON values"
        raise JobValidationError(msg)

    validate(value, 0)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded.encode("utf-8")) > maximum_bytes:
        msg = f"{field_name} exceeds the {maximum_bytes}-byte persistence limit"
        raise JobValidationError(msg)
    return encoded


def _stale_claim_message() -> str:
    return "The job claim is stale, expired, or already settled; no state was changed."
