"""Render-plan layer — decides what to render before serialization.

Pipeline: normalize_to_composition → build_render_plan → execute_render_plan
→ serialize_rendered_plan. Keeps request-aware decisions in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chirp.pages.shell_actions import SHELL_ACTIONS_TARGET
from chirp.templating.composition import PageComposition, RegionUpdate, ViewRef

# OOB region IDs for shell updates (breadcrumbs, sidebar, title) on boosted navigation
CHIRPUI_BREADCRUMBS_TARGET = "chirpui-topbar-breadcrumbs"
CHIRPUI_SIDEBAR_TARGET = "chirpui-sidebar-nav"
CHIRPUI_DOCUMENT_TITLE_TARGET = "chirpui-document-title"
BREADCRUMBS_OOB_BLOCK = "breadcrumbs_oob"
SIDEBAR_OOB_BLOCK = "sidebar_oob"
TITLE_OOB_BLOCK = "title_oob"

# Convention: blocks whose names end with _oob are suppressed during full-page composition
OOB_BLOCK_SUFFIX = "_oob"

# ChirpUI shell OOB blocks — always suppressed on full-page to avoid orphaned fragments
# (breadcrumbs, title, sidebar appear inside app_shell slots; OOB is for HTMX swaps only)
CHIRPUI_OOB_BLOCKS: frozenset[str] = frozenset(
    {BREADCRUMBS_OOB_BLOCK, TITLE_OOB_BLOCK, SIDEBAR_OOB_BLOCK}
)

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.pages.types import LayoutChain
    from chirp.templating.adapter import TemplateAdapter


type RenderIntent = str  # "full_page" | "page_fragment" | "local_fragment"

# Block name → OOB target ID mapping (well-known ChirpUI shell regions)
_OOB_TARGET_MAP: dict[str, str] = {
    BREADCRUMBS_OOB_BLOCK: CHIRPUI_BREADCRUMBS_TARGET,
    SIDEBAR_OOB_BLOCK: CHIRPUI_SIDEBAR_TARGET,
    TITLE_OOB_BLOCK: CHIRPUI_DOCUMENT_TITLE_TARGET,
}


@dataclass(frozen=True, slots=True)
class OOBBlockInfo:
    """AST-derived metadata for a single OOB block in a layout template."""

    block_name: str
    target_id: str
    cache_scope: str
    depends_on: frozenset[str]


@dataclass(frozen=True, slots=True)
class LayoutContract:
    """Cached contract describing which OOB blocks a layout template provides."""

    template_name: str
    oob_blocks: tuple[OOBBlockInfo, ...]


# Module-level cache: template_name → LayoutContract (built once per template)
_layout_contract_cache: dict[str, LayoutContract] = {}


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

    # Breadcrumbs/sidebar OOB added in execute_render_plan when layout has blocks
    # Ensure layout_context has current_path for sidebar active state on boosted nav
    layout_context = dict(composition.context)
    if (
        request
        and layout_chain
        and layout_chain.layouts
        and "current_path" not in layout_context
    ):
        layout_context["current_path"] = request.path

    return RenderPlan(
        intent=intent,
        main_view=main_view,
        render_full_template=render_full_template,
        apply_layouts=apply_layouts,
        layout_chain=layout_chain,
        layout_start_index=layout_start_index,
        layout_context=layout_context,
        region_updates=tuple(region_updates),
    )


def _oob_block_names(adapter: TemplateAdapter, template_name: str) -> set[str]:
    """Return block names ending with _oob for the given template."""
    meta = adapter.template_metadata(template_name)
    if meta is None:
        return set()
    blocks = getattr(meta, "blocks", None)
    if blocks is None:
        return set()
    return {b for b in blocks if b.endswith(OOB_BLOCK_SUFFIX)}


def build_layout_contract(adapter: TemplateAdapter, template_name: str) -> LayoutContract:
    """Build a LayoutContract from Kida's AST metadata for a layout template.

    Discovers all *_oob blocks and extracts their cache_scope and depends_on
    from BlockMetadata. Falls back to well-known ChirpUI OOB blocks when
    template_metadata is unavailable.
    """
    meta = adapter.template_metadata(template_name)
    oob_blocks: list[OOBBlockInfo] = []

    if meta is not None:
        blocks = getattr(meta, "blocks", None) or {}
        for block_name, block_meta in blocks.items():
            if not block_name.endswith(OOB_BLOCK_SUFFIX):
                continue
            target_id = _OOB_TARGET_MAP.get(block_name, block_name.removesuffix(OOB_BLOCK_SUFFIX))
            oob_blocks.append(
                OOBBlockInfo(
                    block_name=block_name,
                    target_id=target_id,
                    cache_scope=getattr(block_meta, "cache_scope", "unknown"),
                    depends_on=frozenset(getattr(block_meta, "depends_on", ())),
                )
            )
    else:
        for block_name, target_id in _OOB_TARGET_MAP.items():
            oob_blocks.append(
                OOBBlockInfo(
                    block_name=block_name,
                    target_id=target_id,
                    cache_scope="unknown",
                    depends_on=frozenset(),
                )
            )

    return LayoutContract(template_name=template_name, oob_blocks=tuple(oob_blocks))


def _get_or_build_contract(adapter: TemplateAdapter, template_name: str) -> LayoutContract:
    """Return cached LayoutContract, building on first access."""
    contract = _layout_contract_cache.get(template_name)
    if contract is None:
        contract = build_layout_contract(adapter, template_name)
        _layout_contract_cache[template_name] = contract
    return contract


def _validate_view_ref(adapter: TemplateAdapter, view: ViewRef) -> None:
    """Validate that a view's block exists. Raises KeyError if missing."""
    if not view.template or not view.block:
        return
    meta = adapter.template_metadata(view.template)
    if meta is None:
        return
    blocks = getattr(meta, "blocks", None)
    if blocks is None:
        return
    if view.block not in blocks:
        raise KeyError(
            f"Block '{view.block}' not found in template '{view.template}'. "
            f"Available blocks: {sorted(blocks.keys())}"
        )


def execute_render_plan(
    plan: RenderPlan,
    *,
    adapter: TemplateAdapter,
    validate_blocks: bool = False,
) -> RenderedPlan:
    """Execute a render plan using the template adapter.

    Args:
        plan: Render plan from build_render_plan.
        adapter: Template engine adapter (e.g., KidaAdapter).
        validate_blocks: When True, validate blocks exist before render.
            Uses adapter.template_metadata() when available. Raises KeyError
            if a block is missing.
    """
    if validate_blocks:
        if not plan.render_full_template:
            _validate_view_ref(adapter, plan.main_view)
        for ru in plan.region_updates:
            if ru.view.template and ru.view.block:
                _validate_view_ref(adapter, ru.view)

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
        # Collect *_oob blocks from ALL layouts (child layouts extend root, which has the blocks)
        # Always include ChirpUI OOB blocks as fallback — template_metadata may fail or
        # return empty; suppressing unknown blocks is safe (no-op if layout has none)
        oob_blocks_to_suppress: set[str] = set(CHIRPUI_OOB_BLOCKS)
        if plan.intent == "full_page":
            for layout_info in layouts:
                oob_blocks_to_suppress |= _oob_block_names(
                    adapter, layout_info.template_name
                )
        for layout_info in reversed(layouts):
            block_overrides: dict[str, str] = {"content": main_html}
            if plan.intent == "full_page":
                for name in oob_blocks_to_suppress:
                    block_overrides[name] = ""
            main_html = adapter.compose_layout(
                layout_info.template_name,
                block_overrides,
                plan.layout_context,
            )

    # Augment region_updates with shell OOB blocks discovered via AST (fragment only)
    region_updates_list: list[RegionUpdate] = list(plan.region_updates)
    if (
        plan.intent == "page_fragment"
        and plan.layout_chain
        and plan.layout_chain.layouts
    ):
        root_layout = plan.layout_chain.layouts[0]
        contract = _get_or_build_contract(adapter, root_layout.template_name)
        layout_ctx = plan.layout_context

        for oob in contract.oob_blocks:
            if oob.cache_scope == "site":
                continue
            if oob.block_name == TITLE_OOB_BLOCK and "page_title" not in layout_ctx:
                continue
            region_updates_list.append(
                RegionUpdate(
                    region=oob.target_id,
                    view=ViewRef(
                        template=root_layout.template_name,
                        block=oob.block_name,
                        context=layout_ctx,
                    ),
                )
            )

    # Render region updates
    region_htmls: dict[str, str] = {}
    for ru in region_updates_list:
        if ru.view.template and ru.view.block:
            try:
                html = adapter.render_block(
                    ru.view.template,
                    ru.view.block,
                    ru.view.context,
                )
            except Exception:
                # Block may not exist (e.g. layout lacks ChirpUI OOB blocks)
                html = ""
        else:
            html = ""
        region_htmls[ru.region] = html

    return RenderedPlan(main_html=main_html, region_htmls=region_htmls)


def serialize_rendered_plan(rendered: RenderedPlan) -> str:
    """Serialize rendered plan to final HTML with OOB fragments."""
    parts: list[str] = [rendered.main_html]
    # innerHTML: replace content inside existing element. outerHTML (true): replace element.
    inner_html_regions = {
        SHELL_ACTIONS_TARGET,
        CHIRPUI_BREADCRUMBS_TARGET,
        CHIRPUI_SIDEBAR_TARGET,
    }
    for region_id, html in rendered.region_htmls.items():
        if region_id == CHIRPUI_DOCUMENT_TITLE_TARGET:
            # title_oob outputs full <title id="..." hx-swap-oob="true">; no div wrapper
            parts.append(html)
        else:
            swap = "innerHTML" if region_id in inner_html_regions else "true"
            parts.append(f'<div id="{region_id}" hx-swap-oob="{swap}">{html}</div>')
    return "\n".join(parts)
