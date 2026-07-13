"""Executable decision inventory for RFC 024 Pelt extraction (#693)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RFC = ROOT / "docs" / "rfcs" / "024-pelt-extraction.md"
pytestmark = pytest.mark.issue(693)


def _rfc() -> str:
    return RFC.read_text(encoding="utf-8")


def _prose() -> str:
    return " ".join(_rfc().split())


def test_rfc_accepts_unambiguous_package_identity_and_provisional_api() -> None:
    text = _rfc()

    assert "**Status:** Accepted — extraction not yet implemented" in text
    assert "`lbliii/bengal-pelt`" in text
    assert "`bengal-pelt`" in text
    assert "`bengal_pelt`" in text
    assert "`0.1.0a1`" in text
    assert "Every `bengal_pelt` 0.x top-level export is provisional" in text

    for name in (
        "AuthenticationError",
        "Connection",
        "ConnectionConfig",
        "PeltConnectionError",
        "PeltError",
        "PeltTimeoutError",
        "Pool",
        "PoolConfig",
        "PostgresError",
        "ProtocolError",
        "TLSError",
        "connect",
        "create_pool",
    ):
        assert name in text


def test_rfc_preserves_database_parameterization_and_dataerror_behavior() -> None:
    text = _prose()

    assert "applications continue to use `chirp.data.Database`" in text
    assert "PostgreSQL `$1`, `$2`, ... placeholders" in text
    assert "`PeltError(Exception)`" in text
    assert "private `DataError` subclass" in text
    assert "`code`, `hint`, `doc`" in text
    assert "`raise ... from exc`" in text
    assert "catches `PeltError`, not `Exception` or `BaseException`" in text


def test_rfc_defines_optional_dependency_and_absence_failure() -> None:
    text = _rfc()

    assert 'data-pg = ["bengal-pelt>=0.1.0a1,<0.2"]' in text
    assert "DriverNotInstalledError" in text
    assert "install bengal-chirp[data-pg]" in text
    assert "SQLite-only `Database` must import and run" in text
    assert "There is no automatic fallback to SQLite or to a bundled driver" in text
    assert "No `AppConfig` field" in text


def test_rfc_assigns_cross_repo_proof_security_and_benchmark_ownership() -> None:
    text = _prose()

    for heading in (
        "## Ownership after extraction",
        "## Test and CI move map",
        "## Security and operational ownership",
        "## Version and release compatibility",
    ):
        assert heading in text

    assert "PostgreSQL 13-18" in text
    assert "minimum supported Pelt and the latest release" in text
    assert "Driver-direct workloads move to Pelt" in text
    assert "pure Python and no native extension" in text


def test_rfc_records_migration_bootstrap_rollback_and_implementation_proof() -> None:
    text = _prose()

    for heading in (
        "## Documentation and migration",
        "## Repository bootstrap and publication order",
        "## Rollback",
        "## Rejected alternatives",
        "## Required implementation proof for #694",
        "## Acceptance for this RFC",
    ):
        assert heading in text

    assert "does not retain `chirp.data.drivers._pelt` as an alias" in text
    assert "Publish `bengal-pelt==0.1.0a1` through Trusted Publishing" in text
    assert "revert the Chirp extraction commits" in text
    assert "No package or runtime change is acceptance evidence for issue #693" in text
