"""Typed hypermedia contracts package."""

from .checker import check_hypermedia_surface
from .declarations import FormContract, FragmentContract, RouteContract, SSEContract, contract
from .types import CheckResult, ContractIssue, Severity

__all__ = [
    "CheckResult",
    "ContractIssue",
    "FormContract",
    "FragmentContract",
    "RouteContract",
    "Severity",
    "SSEContract",
    "check_hypermedia_surface",
    "contract",
]
