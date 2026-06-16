"""Static DOM integrity checks — duplicate ids and dead OOB fragment producers.

Complements browser smoke (#234) with cheaper startup signals for two silent
UI bug classes: invalid duplicate element ids in a template and OOB fragment
blocks that nothing ever renders (#238).
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from collections import Counter
from typing import Any

from chirp.routing.router import Router

from .patterns import ID_ATTR as _ID_PATTERN
from .rules_sse import strip_template_comments
from .types import ContractIssue, Severity

_FRAGMENT_BLOCK_PATTERN = re.compile(
    r"""\{%-?\s*fragment\s+(?P<name>\w+)\s*-?%\}(?P<body>.*?)\{%-?\s*end(?:fragment)?(?:\s+\w+)?\s*-?%\}""",
    re.DOTALL | re.IGNORECASE,
)
_OOB_MARKER_PATTERN = re.compile(r"\bhx-swap-oob\s*=", re.IGNORECASE)


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_arg(node: ast.Call, index: int) -> tuple[bool, str | None]:
    """Return ``(confident, value)`` for a positional string argument."""
    if index >= len(node.args):
        return True, None
    arg = node.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return True, arg.value
    return False, None


def _collect_fragment_calls(node: ast.AST, out: set[tuple[str, str]], blocks: set[str]) -> None:
    """Walk an AST subtree collecting literal Fragment(template, block) pairs."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func_name = _call_name(child.func)
        if func_name == "Fragment":
            ok_tpl, template = _string_arg(child, 0)
            ok_blk, block = _string_arg(child, 1)
            if ok_blk and block:
                blocks.add(block)
                if ok_tpl and template:
                    out.add((template, block))
        elif func_name == "OOB":
            for arg in child.args:
                if not isinstance(arg, ast.Starred):
                    _collect_fragment_calls(arg, out, blocks)


def infer_fragment_producers(handler: Any) -> tuple[set[tuple[str, str]], set[str]]:
    """Infer literal ``Fragment(template, block)`` pairs and block names from *handler*."""
    try:
        source = inspect.getsource(inspect.unwrap(handler))
        tree = ast.parse(textwrap.dedent(source))
    except OSError, SyntaxError, TypeError:
        return set(), set()

    produced: set[tuple[str, str]] = set()
    blocks: set[str] = set()
    _collect_fragment_calls(tree, produced, blocks)
    return produced, blocks


def _function_defs(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def _called_function_names(func_def: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(func_def):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def _nested_functions(
    func_def: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    nested: list[ast.FunctionDef | ast.AsyncFunctionDef] = [func_def]
    nested.extend(
        node
        for node in ast.walk(func_def)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node is not func_def
    )
    return nested


def infer_handler_fragment_blocks(handler: Any) -> set[str]:
    """Infer fragment block names from a handler and its same-module callees."""
    unwrapped = inspect.unwrap(handler)
    module = inspect.getmodule(unwrapped)
    if module is None:
        _pairs, blocks = infer_fragment_producers(handler)
        return blocks
    try:
        module_source = inspect.getsource(module)
        module_tree = ast.parse(textwrap.dedent(module_source))
    except OSError, SyntaxError, TypeError:
        _pairs, blocks = infer_fragment_producers(handler)
        return blocks

    func_map = _function_defs(module_tree)
    handler_def = func_map.get(unwrapped.__name__)
    if handler_def is None:
        _pairs, blocks = infer_fragment_producers(handler)
        return blocks

    produced: set[tuple[str, str]] = set()
    blocks: set[str] = set()
    for fn in _nested_functions(handler_def):
        _collect_fragment_calls(fn, produced, blocks)
    for helper_name in _called_function_names(handler_def):
        helper = func_map.get(helper_name)
        if helper is not None:
            for fn in _nested_functions(helper):
                _collect_fragment_calls(fn, produced, blocks)
    return blocks


def infer_fragment_block_names(handler: Any) -> set[str]:
    """Infer literal fragment block names produced by a handler."""
    _pairs, blocks = infer_fragment_producers(handler)
    return blocks


def collect_fragment_block_producers(
    router: Router,
    signal_registry: Any | None = None,
) -> set[str]:
    """Collect fragment block names produced by routes and signal render callbacks."""
    blocks: set[str] = set()
    for route in router.routes:
        blocks.update(infer_handler_fragment_blocks(route.handler))
    if signal_registry is not None:
        for name in signal_registry.names:
            spec = signal_registry.spec(name)
            if spec is not None and spec.render is not None:
                blocks.update(infer_handler_fragment_blocks(spec.render))
    return blocks


def _extract_oob_fragment_blocks(source: str) -> list[str]:
    """Return fragment block names whose body carries ``hx-swap-oob``."""
    blocks: list[str] = []
    for match in _FRAGMENT_BLOCK_PATTERN.finditer(source):
        body = match.group("body")
        if _OOB_MARKER_PATTERN.search(body):
            blocks.append(match.group("name"))
    return blocks


def _count_static_ids(source: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for match in _ID_PATTERN.finditer(source):
        value = match.group(1).strip()
        if value and "{{" not in value and "{%" not in value:
            counts[value] += 1
    return counts


def _duplicate_ids_in_source(source: str) -> list[tuple[str, int]]:
    """Return static ids repeated in non-fragment markup or within one fragment."""
    source = strip_template_comments(source)
    duplicates: list[tuple[str, int]] = []

    stripped = _FRAGMENT_BLOCK_PATTERN.sub("", source)
    for id_val, count in _count_static_ids(stripped).items():
        if count > 1:
            duplicates.append((id_val, count))

    for match in _FRAGMENT_BLOCK_PATTERN.finditer(source):
        for id_val, count in _count_static_ids(match.group("body")).items():
            if count > 1:
                duplicates.append((id_val, count))

    return duplicates


def check_duplicate_static_ids(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Warn when a template repeats the same static ``id="..."`` value."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        seen: set[str] = set()
        for dup_id, count in _duplicate_ids_in_source(source):
            if dup_id in seen:
                continue
            seen.add(dup_id)
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="duplicate_id",
                    message=(
                        f'Duplicate static id="{dup_id}" appears {count} times in '
                        "this template. Duplicate ids are invalid HTML and break "
                        "getElementById, aria-controls, and htmx targeting."
                    ),
                    template=template_name,
                )
            )
    return issues


def check_oob_fragment_producers(
    template_sources: dict[str, str],
    router: Router,
    signal_registry: Any | None = None,
) -> list[ContractIssue]:
    """Warn when an OOB fragment block has no route/signal handler that renders it."""
    produced_blocks = collect_fragment_block_producers(router, signal_registry)

    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for block_name in _extract_oob_fragment_blocks(source):
            if block_name in produced_blocks:
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="oob_fragment_orphan",
                    message=(
                        f"Fragment '{block_name}' in '{template_name}' is an OOB swap "
                        "payload (contains hx-swap-oob) but no route handler or signal "
                        f"render callback yields Fragment(..., {block_name!r}). The target "
                        "will never update — wire a producer route, EventStream, or "
                        "signal render callback."
                    ),
                    template=template_name,
                )
            )
    return issues
