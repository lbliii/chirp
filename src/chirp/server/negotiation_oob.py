"""OOB helpers for negotiation — shell actions, layout regions, streamed append."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp.pages.shell_actions import (
    SHELL_ACTIONS_CONTEXT_KEY,
    SHELL_ACTIONS_TARGET,
    normalize_shell_actions,
    shell_actions_fragment,
)
from chirp.templating.composition import PageComposition, RegionUpdate, ViewRef
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.integration import render_fragment
from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.oob_registry import OOBRegistry
from chirp.templating.returns import Fragment

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.pages.types import LayoutChain

_log = logging.getLogger(__name__)


def _triggers_shell_update(
    request: Request | None,
    fragment_target_registry: FragmentTargetRegistry | None,
) -> bool:
    """Whether this request should trigger shell OOB updates."""
    if not request or not request.is_fragment or request.is_history_restore:
        return False
    if request.is_boosted:
        return True
    if not request.htmx_target or not fragment_target_registry:
        return False
    config = fragment_target_registry.get(request.htmx_target)
    return config is not None and config.triggers_shell_update


def resolve_oob_scope(
    request: Request | None,
    fragment_target_registry: FragmentTargetRegistry | None,
) -> str | None:
    """Return the scope name for the current swap target, or None.

    Boosted requests default to the broadest scope (``None`` means "all
    scopes").  Non-boosted fragment requests return the registered
    ``scope_name`` so layout OOB blocks can be filtered to the matched
    scope and its ancestors.
    """
    if not request or not request.is_fragment or request.is_history_restore:
        return None
    if request.is_boosted:
        return None
    if not request.htmx_target or not fragment_target_registry:
        return None
    config = fragment_target_registry.get(request.htmx_target)
    if config is None:
        return None
    return config.scope_name


def compute_shell_region_updates(
    composition: PageComposition,
    request: Request | None,
    fragment_target_registry: FragmentTargetRegistry | None,
) -> tuple[RegionUpdate, ...]:
    """Compute shell OOB region updates for boosted/fragment requests."""
    if not _triggers_shell_update(request, fragment_target_registry):
        return ()
    try:
        actions = normalize_shell_actions(composition.context.get(SHELL_ACTIONS_CONTEXT_KEY))
    except TypeError:
        actions = None
    frag = shell_actions_fragment(actions) if actions is not None else None
    if frag is not None:
        template_name, block_name, target = frag
        return (
            RegionUpdate(
                region=target,
                view=ViewRef(
                    template=template_name,
                    block=block_name,
                    context={SHELL_ACTIONS_CONTEXT_KEY: actions},
                ),
            ),
        )
    return (
        RegionUpdate(
            region=SHELL_ACTIONS_TARGET,
            view=ViewRef(template="", block="", context={}),
        ),
    )


def render_shell_actions_oob(context: dict[str, Any], kida_env: Environment) -> str:
    """Render shell action OOB markup for boosted layout navigations."""
    from kida.environment.exceptions import TemplateNotFoundError

    actions = normalize_shell_actions(context.get(SHELL_ACTIONS_CONTEXT_KEY))
    fragment = shell_actions_fragment(actions)
    if fragment is None or actions is None:
        target = SHELL_ACTIONS_TARGET
        html = ""
    else:
        template_name, block_name, target = fragment
        try:
            html = render_fragment(
                kida_env,
                Fragment(template_name, block_name, shell_actions=actions),
            )
        except TemplateNotFoundError:
            html = ""
    return f'<div id="{target}" hx-swap-oob="innerHTML">{html}</div>'


async def append_shell_actions_oob_stream(
    chunks: AsyncIterator[str],
    context: dict[str, Any],
    kida_env: Environment,
) -> AsyncIterator[str]:
    """Append shell action OOB markup to the first streamed chunk."""
    first_chunk = True
    oob = render_shell_actions_oob(context, kida_env)
    async for chunk in chunks:
        if first_chunk:
            yield "\n".join((chunk, oob))
            first_chunk = False
            continue
        yield chunk
    if first_chunk:
        yield oob


def should_append_streamed_shell_actions_oob(
    context: dict[str, Any],
    request: Request | None,
) -> bool:
    """Whether a streamed layout response should refresh shell actions via OOB."""
    del context
    if request is None:
        return False
    return request.is_fragment and not request.is_history_restore and request.is_boosted


def render_layout_oob_blocks(
    kida_env: Environment,
    layout_chain: LayoutChain,
    context: dict[str, Any],
    oob_registry: OOBRegistry | None,
) -> str:
    """Render layout OOB blocks (sidebar, breadcrumbs, title) for boosted navigation.

    Mirrors the OOB region logic in ``execute_render_plan`` but works
    standalone for streaming responses (Suspense, TemplateStream) that
    bypass the render plan pipeline.
    """
    from chirp.templating.render_plan import build_layout_contract

    layouts = getattr(layout_chain, "layouts", ())
    if not layouts:
        return ""

    parts: list[str] = []
    seen_targets: set[str] = set()

    for layout_info in reversed(layouts):
        if oob_registry is not None:
            contract = oob_registry.get_or_build_contract(
                _KidaBlockAdapter(kida_env), layout_info.template_name
            )
        else:
            contract = build_layout_contract(_KidaBlockAdapter(kida_env), layout_info.template_name)

        for oob in contract.oob_blocks:
            if oob.cache_scope == "site" and not oob.depends_on:
                continue
            if "page_title" in oob.depends_on and "page_title" not in context:
                continue
            if oob.target_id in seen_targets:
                continue
            seen_targets.add(oob.target_id)

            try:
                template = kida_env.get_template(layout_info.template_name)
                html = template.render_block(oob.block_name, context)
            except Exception:
                _log.debug("Skipping OOB block %s: render failed", oob.block_name)
                html = ""

            if oob_registry is not None:
                swap, wrap = oob_registry.resolve_serialization(oob.target_id)
            else:
                swap, wrap = "true", True
            if wrap:
                parts.append(f'<div id="{oob.target_id}" hx-swap-oob="{swap}">{html}</div>')
            else:
                parts.append(html)

    return "\n".join(parts)


class _KidaBlockAdapter(KidaAdapter):
    """KidaAdapter with broad error handling for layout contract discovery."""

    def template_metadata(self, template: str) -> object | None:
        try:
            return self._env.get_template(template).template_metadata()
        except Exception:
            return None


def should_append_layout_oob(
    request: Request | None,
    layout_chain: LayoutChain | None,
) -> bool:
    """Whether a streamed layout response should append layout OOB blocks."""
    if request is None or layout_chain is None:
        return False
    if not getattr(layout_chain, "layouts", ()):
        return False
    return request.is_fragment and not request.is_history_restore and request.is_boosted


async def append_layout_oob_stream(
    chunks: AsyncIterator[str],
    kida_env: Environment,
    layout_chain: LayoutChain,
    context: dict[str, Any],
    oob_registry: OOBRegistry | None,
) -> AsyncIterator[str]:
    """Append layout OOB markup (sidebar, breadcrumbs, title) to the first chunk."""
    oob = render_layout_oob_blocks(kida_env, layout_chain, context, oob_registry)
    if not oob:
        async for chunk in chunks:
            yield chunk
        return
    first_chunk = True
    async for chunk in chunks:
        if first_chunk:
            yield "\n".join((chunk, oob))
            first_chunk = False
            continue
        yield chunk
    if first_chunk:
        yield oob
