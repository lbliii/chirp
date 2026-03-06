"""Render-plan layer — decides what to render before serialization.

Pipeline: normalize_to_composition → build_render_plan → execute_render_plan
→ serialize_rendered_plan. Keeps request-aware decisions in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chirp.templating.composition import PageComposition, RegionUpdate, ViewRef

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.pages.types import LayoutChain
    from chirp.templating.adapter import TemplateAdapter


type RenderIntent = str  # "full_page" | "page_fragment" | "local_fragment"


@dataclass(frozen=True, slots=True)
class RenderPlan:
    """Plan for what to render based on composition and request."""

    intent: RenderIntent
    main_view: ViewRef
    render_full_template: bool = False
    apply_layouts: bool = False
    layout_chain: LayoutChain | None = None
    layout_start_index: int = 0
    layout_context: dict[str, Any] = field(default_factory=dict)
    region_updates: tuple[RegionUpdate, ...] = ()
    response_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RenderedPlan:
    """Result of execute_render_plan — main HTML and region HTML by id."""

    main_html: str
    region_htmls: dict[str, str] = field(default_factory=dict)


def _fragment_block_for_request(composition: PageComposition, request: Request | None) -> str:
    """Choose block for htmx fragment response."""
    if request is not None and request.is_boosted:
        return composition.page_block or composition.fragment_block
    return composition.fragment_block


def _should_render_page_block(request: Request | None) -> bool:
    """Whether request needs page-level root instead of narrow fragment."""
    if request is None:
        return True
    if request.is_history_restore or not request.is_fragment:
        return True
    return request.is_boosted


def _compute_layout_start_index(
    layout_chain: LayoutChain | None,
    htmx_target: str | None,
    is_history_restore: bool,
) -> int:
    """Compute layout start index for HX-Target-aware depth."""
    if layout_chain is None or not layout_chain.layouts:
        return 0
    if is_history_restore or htmx_target is None:
        return 0
    idx = layout_chain.find_start_index_for_target(htmx_target)
    if idx is None:
        return len(layout_chain.layouts)
    return idx


def normalize_to_composition(value: Any) -> PageComposition | None:
    """Convert Page, LayoutPage, or PageComposition to PageComposition.

    Returns None for values that are not page-like compositions.
    """
    from chirp.templating.returns import LayoutPage, Page

    if isinstance(value, PageComposition):
        return value
    if isinstance(value, Page):
        return PageComposition(
            template=value.name,
            fragment_block=value.block_name,
            page_block=value.page_block_name or value.block_name,
            context=dict(value.context),
        )
    if isinstance(value, LayoutPage):
        return PageComposition(
            template=value.name,
            fragment_block=value.block_name,
            page_block=value.page_block_name or value.block_name,
            context=dict(value.context),
            layout_chain=value.layout_chain,
            context_providers=value.context_providers,
        )
    return None


def build_render_plan(
    composition: PageComposition,
    *,
    request: Request | None = None,
) -> RenderPlan:
    """Build a render plan from composition and request headers."""
    from chirp.pages.shell_actions import (
        SHELL_ACTIONS_CONTEXT_KEY,
        SHELL_ACTIONS_TARGET,
        normalize_shell_actions,
        shell_actions_fragment,
    )

    layout_chain = composition.layout_chain
    htmx_target = request.htmx_target if request else None
    is_history_restore = request.is_history_restore if request else False
    is_fragment = request.is_fragment if request else False

    # Determine intent and main block
    if not _should_render_page_block(request):
        intent: RenderIntent = "local_fragment"
        block = composition.fragment_block
        apply_layouts = False
        layout_start_index = 0
    elif is_fragment and not is_history_restore:
        intent = "page_fragment"
        block = _fragment_block_for_request(composition, request)
        apply_layouts = layout_chain is not None and bool(layout_chain.layouts)
        layout_start_index = _compute_layout_start_index(
            layout_chain, htmx_target, is_history_restore
        )
    else:
        intent = "full_page"
        block = composition.page_block or composition.fragment_block
        apply_layouts = layout_chain is not None and bool(layout_chain.layouts)
        layout_start_index = 0

    render_full_template = intent == "full_page" and not apply_layouts

    main_view = ViewRef(
        template=composition.template,
        block=block,
        context=composition.context,
    )

    # Build region updates from composition.regions + shell_actions in context
    region_updates: list[RegionUpdate] = list(composition.regions)

    # Add shell_actions as RegionUpdate when applicable (boosted fragment).
    # Always append — when actions is None, we send empty OOB to clear shell.
    if request and request.is_fragment and not request.is_history_restore and request.is_boosted:
        try:
            actions = normalize_shell_actions(composition.context.get(SHELL_ACTIONS_CONTEXT_KEY))
        except TypeError:
            actions = None
        frag = shell_actions_fragment(actions) if actions is not None else None
        if frag is not None:
            template_name, block_name, target = frag
            region_updates.append(
                RegionUpdate(
                    region=target,
                    view=ViewRef(
                        template=template_name,
                        block=block_name,
                        context={SHELL_ACTIONS_CONTEXT_KEY: actions},
                    ),
                )
            )
        else:
            # Empty OOB to clear shell when page has no shell_actions
            region_updates.append(
                RegionUpdate(
                    region=SHELL_ACTIONS_TARGET,
                    view=ViewRef(
                        template="",
                        block="",
                        context={},
                    ),
                )
            )

    return RenderPlan(
        intent=intent,
        main_view=main_view,
        render_full_template=render_full_template,
        apply_layouts=apply_layouts,
        layout_chain=layout_chain,
        layout_start_index=layout_start_index,
        layout_context=composition.context,
        region_updates=tuple(region_updates),
    )


def execute_render_plan(
    plan: RenderPlan,
    *,
    adapter: TemplateAdapter,
) -> RenderedPlan:
    """Execute a render plan using the template adapter."""
    # Render main content
    if plan.render_full_template:
        main_html = adapter.render_template(
            plan.main_view.template,
            plan.main_view.context,
        )
    else:
        main_html = adapter.render_block(
            plan.main_view.template,
            plan.main_view.block,
            plan.main_view.context,
        )

    # Apply layout chain if needed
    if plan.apply_layouts and plan.layout_chain is not None:
        layouts = plan.layout_chain.layouts[plan.layout_start_index :]
        for layout_info in reversed(layouts):
            main_html = adapter.compose_layout(
                layout_info.template_name,
                {"content": main_html},
                plan.layout_context,
            )

    # Render region updates
    region_htmls: dict[str, str] = {}
    for ru in plan.region_updates:
        if ru.view.template and ru.view.block:
            html = adapter.render_block(
                ru.view.template,
                ru.view.block,
                ru.view.context,
            )
        else:
            html = ""
        region_htmls[ru.region] = html

    return RenderedPlan(main_html=main_html, region_htmls=region_htmls)


def serialize_rendered_plan(rendered: RenderedPlan) -> str:
    """Serialize rendered plan to final HTML with OOB fragments."""
    parts: list[str] = [rendered.main_html]
    for region_id, html in rendered.region_htmls.items():
        parts.append(f'<div id="{region_id}" hx-swap-oob="true">{html}</div>')
    return "\n".join(parts)
