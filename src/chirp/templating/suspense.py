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
    2. Render shell with sync context + ``DEFERRED`` sentinel for awaitable
       keys + the ``__chirp_defer_pending__`` frozenset (``CHIRP_DEFER_PENDING_KEY``)
    3. Yield shell as first chunk (instant first paint)
    4. Resolve awaitables concurrently (anyio task group)
    5. Determine blocks to re-render:
       a. If ``defer_blocks`` is set, use that list directly
       b. Otherwise, discover via ``block_metadata().depends_on``
          and prune ancestor blocks (strict ``depends_on`` superset)
    6. Render each block with full context
    7. Yield OOB swap chunks (htmx or <template>+<script>)
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Any

import anyio
from kida import Environment

from chirp.templating.oob_registry import OOBRegistry
from chirp.templating.returns import Suspense

logger = logging.getLogger("chirp.suspense")

if TYPE_CHECKING:
    from chirp.templating.fragment_target_registry import FragmentTargetRegistry

#: Shell / deferred-block template context key for which context keys are
#: still awaiting resolution.  Shell render: ``frozenset`` of deferred names;
#: sync-only renders and deferred block re-renders: empty ``frozenset``.
#: Do not pass a user context key with this name — it is reserved.
CHIRP_DEFER_PENDING_KEY = "__chirp_defer_pending__"


class _Deferred:
    """Sentinel value for Suspense deferred context keys.

    Used instead of ``None`` so that templates can distinguish "not yet loaded"
    from "loaded but empty/falsy".  The ``deferred`` kida test
    (``{% if x is deferred %}``) checks identity against this singleton.

    ``__bool__`` raises ``TypeError`` so that bare ``{% if x %}`` fails loudly
    instead of silently treating a pending value as falsy.
    """

    _instance: _Deferred | None = None

    def __new__(cls) -> _Deferred:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        raise TypeError(
            "Deferred value used in a boolean context. "
            "Use '{% if x is deferred %}' instead of '{% if x %}' — "
            "bare truthiness checks are ambiguous for deferred values."
        )

    def __repr__(self) -> str:
        return "<DEFERRED>"


#: Singleton sentinel for deferred Suspense context values.
#: Use ``{% if x is deferred %}`` in templates to check for this value.
DEFERRED = _Deferred()


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

    If the block's first child element has the same ``id`` as the target,
    ``replaceWith`` is used (outerHTML-style) to avoid double-nesting.
    Otherwise ``innerHTML`` replacement is used.
    """
    escaped_id = target_id.replace('"', "&quot;")
    template_id = f"_chirp_d_{target_id}"
    return (
        f'<template id="{template_id}">{block_html}</template>'
        f"<script>"
        f'(function(){{var t=document.getElementById("{template_id}"),'
        f'e=document.getElementById("{escaped_id}");'
        f"if(t&&e){{var c=t.content.cloneNode(true);"
        f"var f=c.firstElementChild;"
        f'if(f&&f.id==="{escaped_id}"){{e.replaceWith(c);}}'
        f"else{{e.innerHTML='';e.appendChild(c);}}"
        f"t.remove();}}}})();"
        f"</script>"
    )


# ---------------------------------------------------------------------------
# Error fallback rendering
# ---------------------------------------------------------------------------

_DEFAULT_ERROR_HTML = (
    '<div class="chirp-suspense-error" data-block="{block_name}">'
    "Error loading {block_name}</div>"
)


def _render_error_html(
    env: Environment,
    *,
    block_name: str,
    deferred_key: str,
    error: BaseException | None,
    error_template: str | None,
    error_block: str,
    suspense_error_block: str | None,
) -> str:
    """Render error fallback HTML for a failed deferred block.

    Resolution order:
    1. Per-route ``Suspense(error_block=...)`` — block in the same template
       (caller should pass this as *suspense_error_block*)
    2. Global ``error_template`` + ``error_block`` from AppConfig
    3. Hardcoded default HTML
    """
    error_ctx = {
        "error": error,
        "block_name": block_name,
        "deferred_key": deferred_key,
    }

    # 1. Per-route error_block (rendered from global error_template if set)
    tmpl_name = error_template
    blk_name = suspense_error_block or error_block

    if tmpl_name is not None:
        try:
            tmpl = env.get_template(tmpl_name)
            return tmpl.render_block(blk_name, error_ctx)
        except Exception:
            logger.warning(
                "Suspense: failed to render error fallback block=%r from template=%r, "
                "falling back to default error HTML",
                blk_name,
                tmpl_name,
                exc_info=True,
            )

    # 3. Hardcoded default
    return _DEFAULT_ERROR_HTML.format(block_name=block_name)


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

    Parent blocks whose ``depends_on`` is a strict superset of another
    matched block are pruned — they would re-render the entire section
    for an OOB target that likely doesn't exist in the DOM.

    Returns ``{context_key: [block_name, ...]}`` — a key may affect
    multiple blocks, and a block may appear under multiple keys
    (de-duplicated during rendering).
    """
    template = env.get_template(template_name)
    metadata = template.block_metadata()

    key_to_blocks: dict[str, list[str]] = {}

    for block_name, block_meta in metadata.items():
        for dep_path in block_meta.depends_on:
            root_key = dep_path.split(".")[0]
            if root_key in deferred_keys:
                key_to_blocks.setdefault(root_key, []).append(block_name)

    for key, blocks in key_to_blocks.items():
        if len(blocks) <= 1:
            continue
        deps_by_block = {b: metadata[b].depends_on for b in blocks}
        key_to_blocks[key] = _prune_ancestor_blocks(blocks, deps_by_block)

    return key_to_blocks


def _prune_ancestor_blocks(
    blocks: list[str],
    deps_by_block: dict[str, frozenset[str]],
) -> list[str]:
    """Drop blocks whose depends_on is a strict superset of another block's.

    Parent blocks in the AST always accumulate the full dependency set
    of their children.  When both a parent (``page_content``) and a leaf
    (``stats_panel``) match a deferred key, the parent's ``depends_on``
    is a strict superset of the leaf's.  Re-rendering the parent as an
    OOB chunk is expensive and the target id rarely exists in the DOM.
    """
    drop: set[str] = set()
    for a in blocks:
        for b in blocks:
            if a == b:
                continue
            if deps_by_block[a] > deps_by_block[b]:
                drop.add(a)
                break
    return [b for b in blocks if b not in drop]


def _should_wrap_in_layouts(
    layout_chain: Any,
    request: Any,
) -> bool:
    """Return True if the shell should be wrapped in the layout chain."""
    if layout_chain is None or not getattr(layout_chain, "layouts", ()):
        return False
    if request is None:
        return True
    # Mirror LayoutPage: skip layouts for narrow (non-boosted) fragment requests
    return not getattr(request, "is_narrow_fragment", False)


async def render_suspense(
    env: Environment,
    suspense: Suspense,
    *,
    is_htmx: bool = False,
    layout_chain: Any = None,
    layout_context: dict[str, Any] | None = None,
    request: Any = None,
    oob_registry: OOBRegistry | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    error_template: str | None = None,
    error_block: str = "fallback",
) -> AsyncIterator[str]:
    """Render a ``Suspense`` return value as an async chunk stream.

    Yields:
        1. The full page shell (with ``DEFERRED`` sentinel for deferred values
           and ``CHIRP_DEFER_PENDING_KEY`` listing those keys), optionally
           wrapped in the layout chain
        2. One OOB swap chunk per deferred block as its data resolves

    Blocks to re-render are determined by:

    - ``suspense.defer_blocks`` — when set, renders exactly those blocks
      (bypasses static analysis entirely).
    - Otherwise, ``block_metadata().depends_on`` discovers blocks that
      reference deferred context keys, and ancestor blocks are pruned.

    Args:
        env: Kida template environment.
        suspense: The ``Suspense`` return value from a route handler.
        is_htmx: If ``True``, use ``hx-swap-oob`` formatting.
            If ``False``, use ``<template>`` + ``<script>`` pairs.
        layout_chain: Optional layout chain to wrap the shell in.
        layout_context: Context for layout templates (when layout_chain used).
        request: Request for fragment detection (when layout_chain used).
        oob_registry: Optional OOB registry for swap/wrap resolution.
        fragment_target_registry: Optional fragment target registry for
            replace-style boosted navigation that must skip outer layouts.
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

    # -- Early validation: check defer_blocks names before sending the shell --
    # This raises ConfigurationError *before* the shell is sent, so the error
    # is a clean 500 instead of a half-rendered page with frozen skeletons.
    if suspense.defer_blocks is not None and pending:
        template = env.get_template(template_name)
        available = set(template.list_blocks())
        unknown = [b for b in suspense.defer_blocks if b not in available]
        if unknown:
            from chirp.contracts.utils import closest_match
            from chirp.errors import ConfigurationError

            hints = []
            for name in unknown:
                suggestion = closest_match(name, available, max_dist=3)
                if suggestion:
                    hints.append(f"  - '{name}': did you mean '{suggestion}'?")
                else:
                    hints.append(f"  - '{name}'")
            hint_text = "\n".join(hints)
            msg = (
                f"Suspense: defer_blocks contains unknown block(s) "
                f"in template '{template_name}'.\n{hint_text}\n"
                f"Available blocks: {sorted(available)}"
            )
            raise ConfigurationError(msg)

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
            fragment_target_registry=fragment_target_registry,
        )

    # Fast path: no awaitables — render full page in one shot
    if not pending:
        template = env.get_template(template_name)
        sync_ctx = {**sync_ctx, CHIRP_DEFER_PENDING_KEY: frozenset()}
        page_html = template.render(sync_ctx)
        yield _wrap_shell(page_html, {**layout_ctx, **sync_ctx})
        return

    # -- Phase 2: Render shell with DEFERRED sentinel for deferred keys --
    shell_ctx = {
        **sync_ctx,
        **dict.fromkeys(pending, DEFERRED),
        CHIRP_DEFER_PENDING_KEY: frozenset(pending),
    }
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
        logger.warning(
            "Suspense: error resolving deferred context for template=%r, "
            "deferred_keys=%r — shell already sent, replacing skeletons with error indicators",
            template_name,
            sorted(pending.keys()),
            exc_info=True,
        )
        # Shell is already sent; yield a visible error for each pending block
        # so skeletons are replaced with error indicators, not left spinning.
        for key in pending:
            target_id = defer_map.get(key, key)
            fallback_html = _render_error_html(
                env,
                block_name=key,
                deferred_key=key,
                error=None,
                error_template=error_template,
                error_block=error_block,
                suspense_error_block=suspense.error_block,
            )
            if use_htmx_fmt:
                yield format_oob_htmx(fallback_html, target_id)
            else:
                yield format_oob_script(fallback_html, target_id)
        return

    # -- Phase 4: Re-render affected blocks with full context --
    full_ctx = {
        **layout_ctx,
        **sync_ctx,
        **resolved,
        CHIRP_DEFER_PENDING_KEY: frozenset(),
    }

    if suspense.defer_blocks is not None:
        available = set(template.list_blocks())
        unknown = [b for b in suspense.defer_blocks if b not in available]
        if unknown:
            from chirp.contracts.utils import closest_match
            from chirp.errors import ConfigurationError

            hints = []
            for name in unknown:
                suggestion = closest_match(name, available, max_dist=3)
                if suggestion:
                    hints.append(f"  - '{name}': did you mean '{suggestion}'?")
                else:
                    hints.append(f"  - '{name}'")
            hint_text = "\n".join(hints)
            msg = (
                f"Suspense: defer_blocks contains unknown block(s) "
                f"in template '{template_name}'.\n{hint_text}\n"
                f"Available blocks: {sorted(available)}"
            )
            raise ConfigurationError(msg)
        blocks_to_render = [b for b in suspense.defer_blocks if b in available]
    else:
        deferred_keys = set(pending.keys())
        key_to_blocks = _find_deferred_blocks(env, template_name, deferred_keys)
        blocks_to_render = list(
            dict.fromkeys(b for key in deferred_keys for b in key_to_blocks.get(key, []))
        )
        if not blocks_to_render and deferred_keys:
            from chirp.errors import ConfigurationError

            msg = (
                f"Suspense: no blocks discovered for deferred keys "
                f"{sorted(deferred_keys)!r} in template '{template_name}'. "
                f"Deferred data resolved but no OOB swaps will be sent — "
                f"skeletons will remain. Use defer_blocks=(...) to list "
                f"blocks explicitly."
            )
            raise ConfigurationError(msg)

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
            logger.warning(
                "Suspense: error rendering deferred block=%r in template=%r, "
                "target_id=%r — replacing with error indicator",
                block_name,
                template_name,
                target_id,
                exc_info=True,
            )
            error_html = _render_error_html(
                env,
                block_name=block_name,
                deferred_key=block_name,
                error=None,
                error_template=error_template,
                error_block=error_block,
                suspense_error_block=suspense.error_block,
            )
            if use_htmx_fmt:
                yield format_oob_htmx(error_html, target_id)
            else:
                yield format_oob_script(error_html, target_id)
