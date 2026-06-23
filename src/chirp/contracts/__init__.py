"""Typed hypermedia contracts package."""

from .checker import check_hypermedia_surface
from .declarations import FormContract, FragmentContract, RouteContract, SSEContract, contract
from .diff import ContractDiff, diff_contract_dicts
from .serialize import issue_fingerprint, issue_to_dict, result_to_dict
from .surface_diff import (
    check_at_git_ref,
    collect_check_json,
    collect_check_payload,
    collect_surface_diff,
    find_git_root,
    register_surface_diff_tool,
)
from .types import CheckResult, ContractCoverage, ContractIssue, Severity

__all__ = [
    "CheckResult",
    "ContractCoverage",
    "ContractDiff",
    "ContractIssue",
    "FormContract",
    "FragmentContract",
    "RouteContract",
    "SSEContract",
    "Severity",
    "check_at_git_ref",
    "check_hypermedia_surface",
    "collect_check_json",
    "collect_check_payload",
    "collect_surface_diff",
    "contract",
    "diff_contract_dicts",
    "find_git_root",
    "issue_fingerprint",
    "issue_to_dict",
    "register_surface_diff_tool",
    "result_to_dict",
]
