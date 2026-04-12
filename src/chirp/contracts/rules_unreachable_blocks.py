"""Unreachable block detection for filesystem page templates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from kida import Environment
from kida.nodes import Block, Node, Region
from kida.nodes.functions import CallBlock, Def
from kida.nodes.structure import Template as AstTemplate

from .types import ContractIssue, Severity

_DEFAULT_COMPOSITION_ROOTS: frozenset[str] = frozenset({"content", "page_root", "page_content"})


def _composition_roots(extras: dict[str, Any] | None) -> set[str]:
    roots = set(_DEFAULT_COMPOSITION_ROOTS)
    raw = (extras or {}).get("composition_roots")
    if raw is not None:
        roots |= set(raw)
    return roots


def _walk_block_parents(
    nodes: Sequence[Node],
    enclosing: str | None,
    parent_map: dict[str, str | None],
) -> None:
    """Map each block/region name to its nearest enclosing block/region name."""
    for node in nodes:
        if isinstance(node, (Block, Region)):
            parent_map[node.name] = enclosing
            _walk_block_parents(node.body, node.name, parent_map)
            continue
        if isinstance(node, Def):
            _walk_block_parents(node.body, enclosing, parent_map)
            continue
        if isinstance(node, CallBlock):
            for slot_body in node.slots.values():
                _walk_block_parents(slot_body, enclosing, parent_map)
            continue
        if isinstance(node, AstTemplate):
            _walk_block_parents(node.body, enclosing, parent_map)
            continue

        for attr in ("body", "else_", "empty"):
            children = getattr(node, attr, None)
            if children:
                _walk_block_parents(children, enclosing, parent_map)
        elif_ = getattr(node, "elif_", None)
        if elif_:
            for _test, body in elif_:
                _walk_block_parents(body, enclosing, parent_map)
        cases = getattr(node, "cases", None)
        if cases:
            for _pattern, _guard, body in cases:
                _walk_block_parents(body, enclosing, parent_map)


def _block_is_reachable(
    block_name: str,
    roots: set[str],
    parent_map: dict[str, str | None],
) -> bool:
    """True if block_name is a composition root or nested under one."""
    cur: str | None = block_name
    seen: set[str] = set()
    while cur is not None:
        if cur in roots:
            return True
        if cur in seen:
            return False
        seen.add(cur)
        cur = parent_map.get(cur)
    return False


def check_unreachable_blocks(
    page_leaf_templates: set[str],
    kida_env: Environment | None,
    *,
    extras: dict[str, Any] | None = None,
) -> list[ContractIssue]:
    """Detect blocks in page templates that ``render_with_blocks`` cannot reach.

    When Chirp composes filesystem pages into layouts, only the ``content``
    slot (fed from the rendered page block subtree) participates. Blocks that
    are siblings of the composition roots — for example ``page_scripts`` next
    to ``page_root`` — are never rendered and are silently dropped.
    """
    issues: list[ContractIssue] = []
    if not page_leaf_templates or kida_env is None:
        return issues

    roots = _composition_roots(extras)
    details = (
        "Chirp's filesystem page composition injects only the rendered page "
        "block (typically under 'page_root' / 'page_content') into each "
        "layout's 'content' slot. Sibling blocks like 'page_scripts' are not "
        "merged in — unlike {% extends %}, render_with_blocks does not overlay "
        "all blocks from the page template."
    )

    for template_name in sorted(page_leaf_templates):
        try:
            template = kida_env.get_template(template_name)
            page_blocks = template.block_metadata()
        except Exception:
            continue

        if not page_blocks:
            continue

        meta = template.template_metadata()
        if meta is not None and meta.extends is not None:
            continue

        ast = getattr(template, "_optimized_ast", None)
        if ast is None:
            continue

        parent_map: dict[str, str | None] = {}
        _walk_block_parents(ast.body, None, parent_map)

        for block_name in sorted(page_blocks):
            if block_name not in parent_map:
                continue
            if _block_is_reachable(block_name, roots, parent_map):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="unreachable_block",
                    message=(
                        f"Page template '{template_name}' defines block "
                        f"'{block_name}' but it is not reachable via "
                        "render_with_blocks — this block will be silently "
                        "ignored. Place content inside 'page_content' or "
                        "'page_root' instead."
                    ),
                    template=template_name,
                    details=details,
                )
            )

    return issues
