"""Suspense-style streaming — shell first, deferred blocks via OOB.

Renders a page shell immediately with skeleton/fallback content for
blocks whose data is still loading, then streams in the real content
as each async source resolves.

Two delivery strategies (auto-selected by the negotiation layer):

- **htmx navigations**: deferred blocks arrive as ``hx-swap-oob``
  elements that htmx processes automatically.
- **Initial page loads**: ``<template>`` + inline ``<script>`` pairs
  swap content into place without any framework dependency.

Pipeline::

    Suspense("dashboard.html",
        header=site_header(),    # sync — available in the shell
        stats=load_stats(),      # awaitable — deferred
        feed=load_feed(),        # awaitable — deferred
    )

    1. Separate sync vs. awaitable context values
    2. Render shell with sync context + None for awaitable keys
    3. Yield shell as first chunk (instant first paint)
    4. Resolve awaitables concurrently (anyio task group)
    5. For each resolved key, find affected blocks via block_metadata
    6. Render each block with full context
    7. Yield OOB swap chunks (htmx or <template>+<script>)
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import AsyncIterator, Awaitable
from typing import Any

import anyio
from kida import Environment

from chirp.templating.returns import Suspense

logger = logging.getLogger("chirp.suspense")


# ---------------------------------------------------------------------------
# OOB formatters
# ---------------------------------------------------------------------------

def format_oob_htmx(block_html: str, target_id: str) -> str:
    """Wrap rendered block HTML as an htmx OOB swap element.

    htmx scans the response body for elements with ``hx-swap-oob``
    and swaps them into the page by ``id``.
    """
    return f'<div id="{target_id}" hx-swap-oob="true">{block_html}</div>'


def format_oob_script(block_html: str, target_id: str) -> str:
    """Wrap rendered block HTML as a ``<template>`` + ``<script>`` pair.

    Used for initial page loads where htmx OOB is not available.
    The inline script moves template content into the target element.
    """
    # Escape the block HTML for safe embedding inside a <template>
    escaped_id = target_id.replace('"', "&quot;")
    template_id = f"_chirp_d_{target_id}"
    return (
        f'<template id="{template_id}">{block_html}</template>'
        f"<script>"
        f'(function(){{var t=document.getElementById("{template_id}"),'
        f'e=document.getElementById("{escaped_id}");'
        f"if(t&&e){{e.innerHTML='';var c=t.content.cloneNode(true);"
        f"e.appendChild(c);t.remove();}}}})();"
        f"</script>"
    )


# ---------------------------------------------------------------------------
# Core renderer
# ---------------------------------------------------------------------------

def _find_deferred_blocks(
    env: Environment,
    template_name: str,
    deferred_keys: set[str],
) -> dict[str, list[str]]:
    """Map each deferred context key to the template blocks that depend on it.

    Uses kida's ``block_metadata()`` static analysis to find blocks
    whose ``depends_on`` set intersects with the deferred keys.

    Returns ``{context_key: [block_name, ...]}`` — a key may affect
    multiple blocks, and a block may appear under multiple keys
    (de-duplicated during rendering).
    """
    template = env.get_template(template_name)
    metadata = template.block_metadata()

    key_to_blocks: dict[str, list[str]] = {}

    for block_name, block_meta in metadata.items():
        for dep_path in block_meta.depends_on:
            # Match context key: "stats" matches dep path "stats" or "stats.count"
            root_key = dep_path.split(".")[0]
            if root_key in deferred_keys:
                key_to_blocks.setdefault(root_key, []).append(block_name)

    return key_to_blocks


async def render_suspense(
    env: Environment,
    suspense: Suspense,
    *,
    is_htmx: bool = False,
) -> AsyncIterator[str]:
    """Render a ``Suspense`` return value as an async chunk stream.

    Yields:
        1. The full page shell (with ``None`` for deferred values)
        2. One OOB swap chunk per deferred block as its data resolves

    Args:
        env: Kida template environment.
        suspense: The ``Suspense`` return value from a route handler.
        is_htmx: If ``True``, use ``hx-swap-oob`` formatting.
            If ``False``, use ``<template>`` + ``<script>`` pairs.
    """
    context = suspense.context
    template_name = suspense.template_name
    defer_map = suspense.defer_map
    formatter = format_oob_htmx if is_htmx else format_oob_script

    # -- Phase 1: Separate sync vs. async context --
    sync_ctx: dict[str, Any] = {}
    pending: dict[str, Awaitable[Any]] = {}

    for key, value in context.items():
        if inspect.isawaitable(value):
            pending[key] = value
        else:
            sync_ctx[key] = value

    # Fast path: no awaitables — render full page in one shot
    if not pending:
        template = env.get_template(template_name)
        yield template.render(sync_ctx)
        return

    # -- Phase 2: Render shell with None for deferred keys --
    shell_ctx = {**sync_ctx, **dict.fromkeys(pending)}
    template = env.get_template(template_name)
    yield template.render(shell_ctx)

    # -- Phase 3: Resolve awaitables concurrently --
    resolved: dict[str, Any] = {}

    async def _resolve(key: str, awaitable: Awaitable[Any]) -> None:
        resolved[key] = await awaitable

    try:
        async with anyio.create_task_group() as tg:
            for key, awaitable in pending.items():
                tg.start_soon(_resolve, key, awaitable)
    except BaseException:
        logger.exception(
            "Suspense: error resolving deferred context for %s", template_name,
        )
        # Shell is already sent; yield an error comment and stop
        yield "\n<!-- chirp:suspense error resolving deferred data -->\n"
        return

    # -- Phase 4: Re-render affected blocks with full context --
    full_ctx = {**sync_ctx, **resolved}
    deferred_keys = set(pending.keys())
    key_to_blocks = _find_deferred_blocks(env, template_name, deferred_keys)

    # Collect unique blocks to avoid rendering the same block twice
    seen_blocks: set[str] = set()
    blocks_to_render: list[str] = []
    for key in deferred_keys:
        for block_name in key_to_blocks.get(key, []):
            if block_name not in seen_blocks:
                seen_blocks.add(block_name)
                blocks_to_render.append(block_name)

    for block_name in blocks_to_render:
        target_id = defer_map.get(block_name, block_name)
        try:
            block_html = template.render_block(block_name, full_ctx)
            yield formatter(block_html, target_id)
        except Exception:
            logger.exception(
                "Suspense: error rendering deferred block %r for %s",
                block_name, template_name,
            )
            yield f"\n<!-- chirp:suspense error in block {block_name} -->\n"
