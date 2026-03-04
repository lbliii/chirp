"""Tests for contract check diagnostics behavior."""

import pytest

from chirp.app.diagnostics import ContractCheckRunner
from chirp.config import AppConfig
from chirp.contracts import CheckResult, ContractIssue, Severity


def _result_with_warning() -> CheckResult:
    result = CheckResult()
    result.issues.append(
        ContractIssue(
            severity=Severity.WARNING,
            category="page_context",
            message="missing optional page context",
        )
    )
    return result


def _result_with_error() -> CheckResult:
    result = CheckResult()
    result.issues.append(
        ContractIssue(
            severity=Severity.ERROR,
            category="route",
            message="invalid route contract",
        )
    )
    return result


def test_check_allows_warning_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Warnings should not fail checks unless strict warning mode is requested."""
    monkeypatch.setattr(
        "chirp.contracts.check_hypermedia_surface", lambda app: _result_with_warning()
    )
    runner = ContractCheckRunner(AppConfig())
    runner.check(object())


def test_check_fails_when_warnings_as_errors_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strict warning mode should turn warning-only checks into failures."""
    monkeypatch.setattr(
        "chirp.contracts.check_hypermedia_surface", lambda app: _result_with_warning()
    )
    runner = ContractCheckRunner(AppConfig())
    with pytest.raises(SystemExit) as exc_info:
        runner.check(object(), warnings_as_errors=True)
    assert exc_info.value.code == 1


def test_check_still_fails_on_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error behavior must remain unchanged."""
    monkeypatch.setattr(
        "chirp.contracts.check_hypermedia_surface", lambda app: _result_with_error()
    )
    runner = ContractCheckRunner(AppConfig())
    with pytest.raises(SystemExit) as exc_info:
        runner.check(object())
    assert exc_info.value.code == 1
