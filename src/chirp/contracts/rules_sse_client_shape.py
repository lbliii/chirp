"""SSE client-shape contract checks — token swap mode and eager connect."""

import ast
import inspect
import re
import textwrap
from typing import Any

from chirp.routing.router import Router

from .patterns import SSE_CONNECT_TAG as _SSE_CONNECT_TAG_PATTERN
from .routes import build_route_index, find_matching_route
from .rules_sse import (
    _call_name,
    _eventstream_generator_arg,
    _find_nested_funcdef,
    _generator_callable_name,
    _resolve_module_level_generator,
    normalize_sse_url,
    strip_template_comments,
)
from .types import ContractIssue, Severity

_REPLACE_SWAPS = frozenset({"innerhtml", "outerhtml"})
_PAGE_DOC = re.compile(r"<!doctype|<html\b", re.IGNORECASE)
_EAGER_INTENTIONAL = re.compile(r"sse-eager-connect:\s*intentional", re.IGNORECASE)
_SSE_SWAP_TAG = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bsse-swap\s*=\s*[\"']([^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
_HX_SWAP = re.compile(r'\bhx-swap\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_SSE_SWAP_NAME = re.compile(r'\bsse-swap\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


class _FragmentYieldVisitor(ast.NodeVisitor):
    """Classify EventStream generators as one-shot or per-token Fragment yields."""

    def __init__(self) -> None:
        self.loop_depth = 0
        self.outside_loop = 0
        self.inside_loop = False

    def _visit_loop(self, node: ast.AST) -> None:
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node)

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_loop(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) == "Fragment":
            if self.loop_depth > 0:
                self.inside_loop = True
            else:
                self.outside_loop += 1
        self.generic_visit(node)

    def mode(self) -> str | None:
        if self.inside_loop:
            return "multi"
        if self.outside_loop == 1:
            return "single"
        if self.outside_loop > 1:
            return "multi"
        return None


def _resolve_eventstream_generator_tree(handler: Any) -> ast.AST | None:
    try:
        source = inspect.getsource(inspect.unwrap(handler))
        handler_tree = ast.parse(textwrap.dedent(source))
    except OSError, SyntaxError, TypeError:
        return None

    gen_arg = _eventstream_generator_arg(handler_tree)
    if gen_arg is None:
        return None

    gen_name = _generator_callable_name(gen_arg)
    target_tree: ast.AST | None = None
    if gen_name is not None:
        target_tree = _find_nested_funcdef(handler_tree, gen_name)
        if target_tree is None:
            target_tree = _resolve_module_level_generator(handler, gen_name)
    return target_tree or handler_tree


def _eventstream_yield_modes(router: Router) -> dict[str, str]:
    modes: dict[str, str] = {}
    for route in router.routes:
        tree = _resolve_eventstream_generator_tree(route.handler)
        if tree is None:
            continue
        visitor = _FragmentYieldVisitor()
        visitor.visit(tree)
        mode = visitor.mode()
        if mode is not None:
            modes[route.path] = mode
    return modes


def _swap_replaces_content(attrs: str) -> tuple[bool, str]:
    swap_match = _HX_SWAP.search(attrs)
    if swap_match:
        value = swap_match.group(1).strip()
        return value.lower() in _REPLACE_SWAPS, value
    return True, "innerHTML (htmx default)"


def _static_sse_connect_urls(source: str) -> list[str]:
    stripped = strip_template_comments(source)
    urls: list[str] = []
    for match in _SSE_CONNECT_TAG_PATTERN.finditer(stripped):
        raw = match.group("url").strip()
        if "{{" in raw or "{%" in raw:
            continue
        if not raw.startswith("/"):
            continue
        urls.append(normalize_sse_url(raw))
    return urls


def _sse_swap_sinks(source: str) -> list[tuple[str, bool, str]]:
    """Return ``(event_name, replaces, swap_mode)`` for each ``sse-swap`` sink."""
    stripped = strip_template_comments(source)
    sinks: list[tuple[str, bool, str]] = []
    for match in _SSE_SWAP_TAG.finditer(stripped):
        attrs = match.group("attrs")
        event_match = _SSE_SWAP_NAME.search(attrs)
        event_name = event_match.group(1) if event_match else "message"
        replaces, mode = _swap_replaces_content(attrs)
        sinks.append((event_name, replaces, mode))
    return sinks


def check_sse_token_swap_mode(
    template_sources: dict[str, str],
    router: Router,
) -> list[ContractIssue]:
    """Warn when a multi-Fragment SSE stream uses replace swaps instead of append."""
    yield_modes = _eventstream_yield_modes(router)
    if not yield_modes:
        return []

    multi_routes = {path for path, mode in yield_modes.items() if mode == "multi"}
    if not multi_routes:
        return []

    route_paths = {path: frozenset() for path in multi_routes}
    static_routes, parametric_routes = build_route_index(route_paths)
    issues: list[ContractIssue] = []

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        connect_urls = _static_sse_connect_urls(source)
        if not connect_urls:
            continue
        sinks = _sse_swap_sinks(source)
        if not sinks:
            continue

        matched_multi: set[str] = set()
        for url in connect_urls:
            route_match = find_matching_route(url, static_routes, parametric_routes)
            if route_match is None:
                continue
            matched_route, _ = route_match
            if matched_route in multi_routes:
                matched_multi.add(matched_route)

        if not matched_multi:
            continue

        for _event_name, replaces, swap_mode in sinks:
            if not replaces:
                continue
            routes_text = ", ".join(sorted(matched_multi))
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="sse_token_swap_mode",
                    message=(
                        f'Template "{template_name}" listens to SSE route(s) '
                        f"({routes_text}) that yield many small Fragments, but "
                        f'the sse-swap sink uses hx-swap="{swap_mode}" (replace). '
                        "Per-token streams should append with "
                        'hx-swap="beforeend" (or afterend).'
                    ),
                    template=template_name,
                    route=routes_text,
                )
            )
            break

    return issues


def check_sse_eager_connect(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Info when a full page statically connects to SSE on first paint."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        if _EAGER_INTENTIONAL.search(source):
            continue
        stripped = strip_template_comments(source)
        if not _PAGE_DOC.search(stripped):
            continue
        for match in _SSE_CONNECT_TAG_PATTERN.finditer(stripped):
            raw = match.group("url").strip()
            if "{{" in raw or "{%" in raw:
                continue
            if not raw.startswith("/"):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="sse_eager_connect",
                    message=(
                        f'static sse-connect="{raw}" in "{template_name}" starts '
                        "streaming on page load. Prefer POST → Fragment with a "
                        "parametric connect URL when the stream should begin after "
                        "user action. Mark intentional live feeds with "
                        "{# sse-eager-connect: intentional #}."
                    ),
                    template=template_name,
                )
            )
            break
    return issues
