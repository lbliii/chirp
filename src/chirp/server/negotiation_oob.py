"""OOB helpers for negotiation — shell actions, streamed append."""

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
from chirp.templating.returns import Fragment

if TYPE_CHECKING:
    from chirp.http.request import Request


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
