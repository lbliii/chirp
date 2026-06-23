"""Stable JSON serialization for hypermedia contract check results."""

from __future__ import annotations

from typing import Any

from chirp.contracts.types import CheckResult, ContractIssue, Severity


def issue_fingerprint(issue: ContractIssue) -> tuple[str, str, str, str, str]:
    """Deterministic identity for diffing issues across runs."""
    return (
        issue.severity.value,
        issue.category,
        issue.route or "",
        issue.template or "",
        issue.message,
    )


def issue_to_dict(issue: ContractIssue) -> dict[str, Any]:
    """Serialize one issue for JSON baselines."""
    return {
        "severity": issue.severity.value,
        "category": issue.category,
        "message": issue.message,
        "template": issue.template,
        "route": issue.route,
        "details": issue.details,
    }


def result_to_dict(
    result: CheckResult,
    *,
    include_info: bool = False,
) -> dict[str, Any]:
    """Serialize a :class:`CheckResult` for ``chirp check --json`` baselines."""
    issues = result.issues
    if not include_info:
        issues = [i for i in issues if i.severity is not Severity.INFO]
    serialized = [issue_to_dict(i) for i in issues]
    serialized.sort(
        key=lambda item: (
            item["severity"],
            item["category"],
            item["route"] or "",
            item["template"] or "",
            item["message"],
        )
    )
    return {
        "ok": result.ok,
        "routes_checked": result.routes_checked,
        "templates_scanned": result.templates_scanned,
        "issues": serialized,
    }
