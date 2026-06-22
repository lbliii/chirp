"""Contract checks for per-record access grant usage."""

from __future__ import annotations

import ast
import inspect
from typing import Any

from chirp.routing.router import Router

from .types import ContractIssue, Severity

_SCALAR_ACCESS_CALLS = frozenset({"check_access", "require_access", "has_access"})


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _ScalarAccessInLoopFinder(ast.NodeVisitor):
    """Detect scalar grant checks inside iteration (N+1 list-render trap)."""

    def __init__(self) -> None:
        self.found: list[tuple[int, str]] = []
        self._loop_depth = 0

    def visit_For(self, node: ast.For) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if self._loop_depth > 0 and name in _SCALAR_ACCESS_CALLS:
            self.found.append((node.lineno, name or "<call>"))
        self.generic_visit(node)


def _analyze_handler(source: str) -> _ScalarAccessInLoopFinder | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    finder = _ScalarAccessInLoopFinder()
    finder.visit(tree)
    return finder if finder.found else None


def check_access_grant_scalar_loops(
    router: Router,
    config: Any,
) -> list[ContractIssue]:
    """Flag per-row scalar ``check_access`` calls inside handler loops.

    List fragments should use :meth:`~chirp.data.Query.accessible_to` (set-based)
    instead of calling ``check_access`` once per row. Env-aware like
    ``sse_auth_gate``: ERROR in production, WARNING in staging, silent in
    development.
    """
    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return []
    severity = Severity.ERROR if env == "production" else Severity.WARNING

    issues: list[ContractIssue] = []
    for route in getattr(router, "routes", []):
        handler = getattr(route, "handler", None)
        if handler is None:
            continue
        try:
            source = inspect.getsource(handler)
        except OSError, TypeError:
            continue
        source = inspect.cleandoc(source)
        finder = _analyze_handler(source)
        if finder is None:
            continue
        path = getattr(route, "path", None) or "<route>"
        for lineno, name in finder.found:
            issues.append(
                ContractIssue(
                    severity=severity,
                    category="access_grant_scalar_loop",
                    message=(
                        f"Route '{path}' calls {name}() inside a loop (line {lineno}). "
                        "Use Query.accessible_to(user, perm, resource_type=...) for "
                        "set-based list filtering instead of per-row scalar checks."
                    ),
                    route=path,
                )
            )
    return issues
