"""Typed hypermedia contracts package."""

from .checker import check_hypermedia_surface
from .declarations import FormContract, FragmentContract, RouteContract, SSEContract, contract
from .diff import ContractDiff, diff_contract_dicts
from .serialize import issue_fingerprint, issue_to_dict, result_to_dict
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
    "check_hypermedia_surface",
    "contract",
    "diff_contract_dicts",
    "issue_fingerprint",
    "issue_to_dict",
    "result_to_dict",
]
