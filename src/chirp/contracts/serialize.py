"""Stable JSON serialization for hypermedia contract check results."""

from __future__ import annotations

from typing import Any

from chirp.contracts.types import CheckResult, ContractCoverage, ContractIssue, Severity


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
    include_coverage: bool = False,
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
    payload = {
        "ok": result.ok,
        "routes_checked": result.routes_checked,
        "templates_scanned": result.templates_scanned,
        "issues": serialized,
    }
    if include_coverage:
        payload["coverage"] = coverage_to_dict(result.coverage)
    return payload


def coverage_to_dict(coverage: ContractCoverage) -> dict[str, int]:
    """Serialize coverage counters without changing default CLI JSON."""
    return {
        "post_routes": coverage.post_routes,
        "post_routes_with_form_contract": coverage.post_routes_with_form_contract,
        "mounted_page_routes": coverage.mounted_page_routes,
        "mounted_page_routes_with_contract": coverage.mounted_page_routes_with_contract,
        "page_shell_contracts": coverage.page_shell_contracts,
        "page_shell_required_blocks": coverage.page_shell_required_blocks,
        "fragment_targets_registered": coverage.fragment_targets_registered,
        "oob_regions_registered": coverage.oob_regions_registered,
        "webmcp_projections_declared": coverage.webmcp_projections_declared,
        "webmcp_projections_compiled": coverage.webmcp_projections_compiled,
        "webmcp_parameters_declared": coverage.webmcp_parameters_declared,
    }
