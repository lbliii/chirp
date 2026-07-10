"""Private Phase 1 durable-job boundaries for issue #677."""

from __future__ import annotations

import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest

from chirp import App
from chirp.data._jobs import (
    EnqueueResult,
    JobMigrationRequiredError,
    JobProgress,
    JobSchemaVersionError,
    JobStoreError,
    JobValidationError,
    PostgresJobStore,
    migration_directory,
)
from chirp.data.database import Database
from chirp.data.errors import QueryError
from chirp.data.migrate import _discover_migrations
from chirp.testing import TestClient

_ROOT = Path(__file__).resolve().parents[1]


class _MissingTableError(Exception):
    sqlstate = "42P01"


class _Connection:
    def __init__(self, row: dict[str, object] | None = None, error: Exception | None = None):
        self.row = row
        self.error = error

    async def fetchrow(self, _sql: str, *_params: object) -> dict[str, object] | None:
        if self.error is not None:
            raise self.error
        return self.row

    async def execute(self, _sql: str, *_params: object) -> str:
        if self.error is not None:
            raise self.error
        return "UPDATE 0"


class _FakeDatabase:
    _driver = "postgresql"

    def __init__(self, connection: _Connection):
        self.connection = connection

    @asynccontextmanager
    async def _connection(self, *, write: bool = False):
        del write
        yield self.connection


def _store(connection: _Connection) -> PostgresJobStore:
    database = cast(Database, cast(Any, _FakeDatabase(connection)))
    return PostgresJobStore(database)


@pytest.mark.issue(677)
def test_private_store_rejects_sqlite_without_connecting() -> None:
    database = Database("sqlite:///:memory:")

    with pytest.raises(JobStoreError, match="requires a PostgreSQL Database"):
        PostgresJobStore(database)

    assert database._initialized is False


@pytest.mark.issue(677)
def test_store_records_are_frozen_and_slotted() -> None:
    result = EnqueueResult(job_id=__import__("uuid").uuid4(), created=True)

    assert result.__dataclass_params__.frozen is True
    assert not hasattr(result, "__dict__")


@pytest.mark.issue(677)
async def test_missing_migration_fails_with_actionable_redacted_guidance() -> None:
    store = _store(_Connection(error=_MissingTableError("secret database detail")))

    with pytest.raises(JobMigrationRequiredError) as caught:
        await store.check_ready()

    message = str(caught.value)
    assert "001_durable_jobs.sql" in message
    assert "chirp migrate" in message
    assert "secret" not in message


@pytest.mark.issue(677)
async def test_unknown_schema_version_fails_loud() -> None:
    store = _store(_Connection(row={"version": 99}))

    with pytest.raises(JobSchemaVersionError, match="expected 1, found 99"):
        await store.check_ready()


@pytest.mark.issue(677)
async def test_database_failures_redact_bound_values() -> None:
    store = _store(_Connection(error=RuntimeError("payload=customer-secret")))

    with pytest.raises(QueryError) as caught:
        await store._execute("UPDATE fixed_sql SET payload = $1", "customer-secret")

    assert "bound values were redacted" in str(caught.value)
    assert "customer-secret" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.issue(677)
@pytest.mark.parametrize(
    "payload",
    [
        object(),
        ("tuple",),
        {1: "non-string-key"},
        {"number": float("nan")},
        {"number": float("inf")},
    ],
)
async def test_enqueue_rejects_non_json_payloads_before_database_access(payload: object) -> None:
    store = PostgresJobStore(Database("postgresql://unused/unused"))

    with pytest.raises(JobValidationError, match="payload"):
        await store.enqueue("jobs.example", payload, payload_version=1)

    assert store._db._initialized is False


@pytest.mark.issue(677)
async def test_enqueue_rejects_oversized_and_deep_payloads_before_database_access() -> None:
    store = PostgresJobStore(Database("postgresql://unused/unused"))
    deep: object = None
    for _ in range(34):
        deep = [deep]

    with pytest.raises(JobValidationError, match="65536-byte"):
        await store.enqueue("jobs.example", {"value": "x" * 65_536}, payload_version=1)
    with pytest.raises(JobValidationError, match="nesting depth"):
        await store.enqueue("jobs.example", deep, payload_version=1)

    assert store._db._initialized is False


@pytest.mark.issue(677)
async def test_progress_and_failure_validation_never_echoes_values() -> None:
    store = PostgresJobStore(Database("postgresql://unused/unused"))
    secret = "sensitive-value"

    with pytest.raises(JobValidationError) as progress_error:
        await store.update_progress(
            cast(Any, None),
            JobProgress(status=secret * 100, step=0, total=0),
        )
    with pytest.raises(JobValidationError) as enqueue_error:
        await store.enqueue(
            "jobs.example",
            {},
            payload_version=1,
            idempotency_key=secret * 100,
        )

    assert secret not in str(progress_error.value)
    assert secret not in str(enqueue_error.value)


@pytest.mark.issue(677)
def test_checked_in_migration_is_reviewable_deterministic_and_packaged() -> None:
    migrations = _discover_migrations(migration_directory())
    assert [(migration.version, migration.name) for migration in migrations] == [
        (1, "001_durable_jobs")
    ]
    sql = migrations[0].sql
    assert "CREATE TABLE _chirp_job_schema" in sql
    assert "CREATE TABLE _chirp_job_queues" in sql
    assert "CREATE TABLE _chirp_jobs" in sql
    assert "FOR UPDATE" not in sql
    assert "IF NOT EXISTS" not in sql

    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"data/migrations/**/*.sql"' in pyproject
    workflow = (_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.count("tests/test_jobs_postgres.py") == 2
    assert "data-pg-gil-gate:" in workflow


@pytest.mark.issue(677)
def test_runtime_source_contains_no_ddl_or_public_export() -> None:
    source = (_ROOT / "src/chirp/data/_jobs.py").read_text(encoding="utf-8")
    data_init = (_ROOT / "src/chirp/data/__init__.py").read_text(encoding="utf-8")
    top_init = (_ROOT / "src/chirp/__init__.py").read_text(encoding="utf-8")

    assert "CREATE TABLE" not in source
    assert "ALTER TABLE" not in source
    assert "PostgresJobStore" not in data_init
    assert "PostgresJobStore" not in top_init


@pytest.mark.issue(677)
def test_importing_chirp_does_not_import_or_connect_the_job_domain() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import chirp; "
                "assert 'chirp.data._jobs' not in sys.modules; "
                "assert 'chirp.data.database' not in sys.modules"
            ),
        ],
        cwd=_ROOT,
        check=True,
    )


@pytest.mark.issue(677)
async def test_html_only_app_never_connects_or_creates_job_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_connect(_database: Database) -> None:
        raise AssertionError("an HTML-only app must not connect a database")

    monkeypatch.setattr(Database, "connect", unexpected_connect)
    app = App()

    @app.route("/")
    def index() -> str:
        return "<h1>HTML only</h1>"

    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.status == 200
    assert response.text == "<h1>HTML only</h1>"
