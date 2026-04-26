"""Typed hypermedia contracts package."""

from .checker import check_hypermedia_surface
from .declarations import FormContract, FragmentContract, RouteContract, SSEContract, contract
from .types import CheckResult, ContractCoverage, ContractIssue, Severity

__all__ = [
    "CheckResult",
    "ContractCoverage",
    "ContractIssue",
    "FormContract",
    "FragmentContract",
    "RouteContract",
    "SSEContract",
    "Severity",
    "check_hypermedia_surface",
    "contract",
]
