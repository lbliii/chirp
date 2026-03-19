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

from chirp.templating.oob_registry import OOBRegistry
from chirp.templating.returns import Suspense

logger = logging.getLogger("chirp.suspense")


# ---------------------------------------------------------------------------
# OOB formatters
# ---------------------------------------------------------------------------


def format_oob_htmx(
    block_html: str,
    target_id: str,
    swap: str = "true",
    *,
    wrap: bool = True,
) -> str:
    """Wrap rendered block HTML as an htmx OOB swap element.

    htmx scans the response body for elements with ``hx-swap-oob``
    and swaps them into the page by ``id``.
    """
    if not wrap:
        return block_html
    return f'<div id="{target_id}" hx-swap-oob="{swap}">{block_html}</div>'


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


def _should_wrap_in_layouts(
    layout_chain: Any,
    request: Any,
) -> bool:
    """Return True if the shell should be wrapped in the layout chain."""
    if layout_chain is None or not getattr(layout_chain, "layouts", ()):
        return False
    if request is None:
        return True
    # Mirror LayoutPage: skip layouts for non-boosted fragment requests
    return not (
        getattr(request, "is_fragment", False)
        and not getattr(request, "is_history_restore", False)
        and not getattr(request, "is_boosted", False)
    )


async def render_suspense(
    env: Environment,
    suspense: Suspense,
    *,
    is_htmx: bool = False,
    layout_chain: Any = None,
    layout_context: dict[str, Any] | None = None,
    request: Any = None,
    oob_registry: OOBRegistry | None = None,
) -> AsyncIterator[str]:
    """Render a ``Suspense`` return value as an async chunk stream.

    Yields:
        1. The full page shell (with ``None`` for deferred values),
           optionally wrapped in the layout chain
        2. One OOB swap chunk per deferred block as its data resolves

    Args:
        env: Kida template environment.
        suspense: The ``Suspense`` return value from a route handler.
        is_htmx: If ``True``, use ``hx-swap-oob`` formatting.
            If ``False``, use ``<template>`` + ``<script>`` pairs.
        layout_chain: Optional layout chain to wrap the shell in.
        layout_context: Context for layout templates (when layout_chain used).
        request: Request for fragment detection (when layout_chain used).
    """
    context = suspense.context
    template_name = suspense.template_name
    defer_map = suspense.defer_map
    use_htmx_fmt = is_htmx

    layout_ctx = layout_context if layout_context is not None else {}

    # -- Phase 1: Separate sync vs. async context --
    # Merge layout_context (cascade: shell_actions, current_user) so template can access it
    sync_ctx: dict[str, Any] = {}
    pending: dict[str, Awaitable[Any]] = {}

    for key, value in {**layout_ctx, **context}.items():
        if inspect.isawaitable(value):
            pending[key] = value
        else:
            sync_ctx[key] = value

    def _wrap_shell(page_html: str, ctx: dict[str, Any]) -> str:
        if not _should_wrap_in_layouts(layout_chain, request):
            return page_html
        from chirp.pages.renderer import render_with_layouts

        htmx_target = getattr(request, "htmx_target", None) if request else None
        is_history_restore = getattr(request, "is_history_restore", False) if request else False
        return render_with_layouts(
            env,
            layout_chain=layout_chain,
            page_html=page_html,
            context=ctx,
            htmx_target=htmx_target,
            is_history_restore=is_history_restore,
        )

    # Fast path: no awaitables — render full page in one shot
    if not pending:
        template = env.get_template(template_name)
        page_html = template.render(sync_ctx)
        yield _wrap_shell(page_html, {**layout_ctx, **sync_ctx})
        return

    # -- Phase 2: Render shell with None for deferred keys --
    shell_ctx = {**sync_ctx, **dict.fromkeys(pending)}
    template = env.get_template(template_name)
    page_html = template.render(shell_ctx)
    yield _wrap_shell(page_html, {**layout_ctx, **shell_ctx})

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
            "Suspense: error resolving deferred context for %s",
            template_name,
        )
        # Shell is already sent; yield an error comment and stop
        yield "\n<!-- chirp:suspense error resolving deferred data -->\n"
        return

    # -- Phase 4: Re-render affected blocks with full context --
    full_ctx = {**layout_ctx, **sync_ctx, **resolved}
    deferred_keys = set(pending.keys())
    key_to_blocks = _find_deferred_blocks(env, template_name, deferred_keys)

    # Collect unique blocks (order-preserving dedup)
    blocks_to_render = list(
        dict.fromkeys(
            b for key in deferred_keys for b in key_to_blocks.get(key, [])
        )
    )

    for block_name in blocks_to_render:
        target_id = defer_map.get(block_name, block_name)
        try:
            block_html = template.render_block(block_name, full_ctx)
            if use_htmx_fmt:
                if oob_registry is not None:
                    swap, wrap = oob_registry.resolve_serialization(target_id)
                else:
                    swap, wrap = "true", True
                yield format_oob_htmx(block_html, target_id, swap, wrap=wrap)
            else:
                yield format_oob_script(block_html, target_id)
        except Exception:
            logger.exception(
                "Suspense: error rendering deferred block %r for %s",
                block_name,
                template_name,
            )
            yield f"\n<!-- chirp:suspense error in block {block_name} -->\n"
