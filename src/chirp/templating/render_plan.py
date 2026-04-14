"""Render-plan layer — decides what to render before serialization.

Pipeline: normalize_to_composition → build_render_plan → execute_render_plan
→ serialize_rendered_plan. Keeps request-aware decisions in one place.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chirp.pages.types import LayoutChain
from chirp.shell_actions import SHELL_ACTIONS_TARGET
from chirp.templating.composition import PageComposition, RegionUpdate, ViewRef
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.oob_registry import OOB_BLOCK_SUFFIX, OOBRegistry

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.templating.adapter import TemplateAdapter


type RenderIntent = str  # "full_page" | "page_fragment" | "local_fragment"


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
    include_layout_oob: bool = False
    oob_scope: str | None = None


@dataclass(frozen=True, slots=True)
class RenderedPlan:
    """Result of execute_render_plan — main HTML and region HTML by id."""

    main_html: str
    region_htmls: dict[str, str] = field(default_factory=dict)


# Fallback when no fragment_target_registry: targets that expect fragment_block
_CONTENT_ONLY_TARGETS: frozenset[str] = frozenset({"page-content-inner", "page-root"})


def _resolve_fragment_block(
    composition: PageComposition,
    request: Request | None,
    *,
    fragment_target_registry: FragmentTargetRegistry | None = None,
) -> str:
    """Resolve fragment block: explicit > htmx partial > HX-Target registry lookup > fallback."""
    if composition.fragment_block is not None:
        return composition.fragment_block
    # htmx 4.0+: <htmx-partial> element name maps to a registered block
    if request and fragment_target_registry:
        htmx = getattr(request, "htmx", None)
        partial_name = getattr(htmx, "partial", None) if htmx is not None else None
        if partial_name:
            config = fragment_target_registry.get(partial_name)
            if config is not None:
                return config.fragment_block
    if request and request.htmx_target and fragment_target_registry:
        config = fragment_target_registry.get(request.htmx_target)
        if config is not None:
            return config.fragment_block
        registered_targets = sorted(fragment_target_registry.registered_targets)
        _log.warning(
            "Unregistered HX-Target %r; falling back to '%s'. "
            "Register with app.register_fragment_target() or "
            "app.register_page_shell_contract() if this target expects a "
            "different block. Registered targets: %s",
            request.htmx_target,
            composition.page_block or "page_content",
            registered_targets,
        )
    return composition.page_block or "page_content"


def _fragment_block_for_request(
    composition: PageComposition,
    request: Request | None,
    *,
    layout_chain: LayoutChain | None = None,
    layout_start_index: int = 0,
    fragment_target_registry: FragmentTargetRegistry | None = None,
) -> str:
    """Choose block for htmx fragment response."""
    if request is None or not request.is_boosted:
        return _resolve_fragment_block(
            composition, request, fragment_target_registry=fragment_target_registry
        )
    if layout_chain is None or layout_start_index >= len(layout_chain.layouts):
        return (
            composition.page_block
            or composition.fragment_block
            or _resolve_fragment_block(
                composition, request, fragment_target_registry=fragment_target_registry
            )
        )
    target_layout = layout_chain.layouts[layout_start_index]
    target_id = target_layout.target
    if fragment_target_registry is not None:
        if fragment_target_registry.is_content_target(target_id):
            config = fragment_target_registry.get(target_id)
            if config is not None:
                return config.fragment_block
        return composition.page_block or _resolve_fragment_block(
            composition, request, fragment_target_registry=fragment_target_registry
        )
    # Fallback: legacy hardcoded targets
    if target_id in _CONTENT_ONLY_TARGETS:
        return _resolve_fragment_block(
            composition, request, fragment_target_registry=fragment_target_registry
        )
    return composition.page_block or _resolve_fragment_block(
        composition, request, fragment_target_registry=fragment_target_registry
    )


def _should_render_page_block(request: Request | None) -> bool:
    """Whether request needs page-level root instead of narrow fragment."""
    if request is None:
        return True
    if request.is_history_restore or not request.is_htmx:
        return True
    return request.is_boosted


def _compute_layout_start_index(
    layout_chain: LayoutChain | None,
    htmx_target: str | None,
    is_history_restore: bool,
    *,
    fragment_target_registry: FragmentTargetRegistry | None = None,
) -> int:
    """Compute layout start index for HX-Target-aware depth."""
    if layout_chain is None or not layout_chain.layouts:
        return 0
    if is_history_restore or htmx_target is None:
        return 0
    omit_targets = frozenset()
    if fragment_target_registry is not None:
        config = fragment_target_registry.get(htmx_target)
        if config is not None and config.omit_outer_layouts:
            omit_targets = frozenset({htmx_target.lstrip("#")})
    idx = layout_chain.start_index_for_htmx_target(
        htmx_target,
        omit_outer_layout_targets=omit_targets,
    )
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
            template=value.template_name,
            fragment_block=value.block_name,
            page_block=value.page_block_name or value.block_name,
            context=dict(value.context),
        )
    if isinstance(value, LayoutPage):
        return PageComposition(
            template=value.template_name,
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
    fragment_target_registry: FragmentTargetRegistry | None = None,
    shell_region_updates: tuple[RegionUpdate, ...] = (),
) -> RenderPlan:
    """Build a render plan from composition and request headers."""
    layout_chain = composition.layout_chain
    htmx_target = request.htmx_target if request else None
    is_history_restore = request.is_history_restore if request else False
    is_htmx = request.is_htmx if request else False

    # Determine intent and main block
    if not _should_render_page_block(request):
        intent: RenderIntent = "local_fragment"
        block = _resolve_fragment_block(
            composition, request, fragment_target_registry=fragment_target_registry
        )
        apply_layouts = False
        layout_start_index = 0
    elif is_htmx and not is_history_restore:
        intent = "page_fragment"
        apply_layouts = layout_chain is not None and bool(layout_chain.layouts)
        layout_start_index = _compute_layout_start_index(
            layout_chain,
            htmx_target,
            is_history_restore,
            fragment_target_registry=fragment_target_registry,
        )
        block = _fragment_block_for_request(
            composition,
            request,
            layout_chain=layout_chain,
            layout_start_index=layout_start_index,
            fragment_target_registry=fragment_target_registry,
        )
    else:
        intent = "full_page"
        block = composition.page_block or composition.fragment_block or "page_root"
        apply_layouts = layout_chain is not None and bool(layout_chain.layouts)
        layout_start_index = 0

    render_full_template = intent == "full_page" and not apply_layouts

    main_view = ViewRef(
        template=composition.template,
        block=block,
        context=composition.context,
    )

    # Build region updates from composition.regions + pre-computed shell updates
    region_updates = composition.regions + shell_region_updates

    # Include layout OOB for page_fragment or when shell updates were added
    triggers_shell = bool(shell_region_updates)
    include_layout_oob = intent == "page_fragment" or triggers_shell

    # Resolve OOB scope from the target's registered scope_name.
    # None means "all scopes" (boosted nav or no target); a string limits
    # layout OOB to the matched scope level and its ancestors.
    oob_scope: str | None = None
    if htmx_target and fragment_target_registry:
        config = fragment_target_registry.get(htmx_target)
        if config is not None:
            oob_scope = config.scope_name

    # Ensure layout_context has current_path for sidebar active state
    layout_context = dict(composition.context)
    if request and layout_chain and layout_chain.layouts and "current_path" not in layout_context:
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
        include_layout_oob=include_layout_oob,
        oob_scope=oob_scope,
    )


def _oob_block_names(adapter: TemplateAdapter, template_name: str) -> set[str]:
    """Return block names ending with _oob for the given template.

    Prefers meta.regions() when available (region-typed blocks); otherwise
    filters meta.blocks by *_oob suffix. Falls back to empty set when
    template_metadata is unavailable (e.g. Jinja2 adapter).
    """
    meta = adapter.template_metadata(template_name)
    if meta is None:
        return set()
    # Prefer regions() when available (Kida); fallback to blocks
    regions = getattr(meta, "regions", None)
    if callable(regions):
        region_blocks = regions()
        if region_blocks is not None:
            return {b for b in region_blocks if b.endswith(OOB_BLOCK_SUFFIX)}
    blocks = getattr(meta, "blocks", None)
    if blocks is None:
        return set()
    return {b for b in blocks if b.endswith(OOB_BLOCK_SUFFIX)}


def build_layout_contract(
    adapter: TemplateAdapter,
    template_name: str,
    *,
    oob_registry: OOBRegistry | None = None,
) -> LayoutContract:
    """Build a LayoutContract from Kida's AST metadata for a layout template.

    Discovers all *_oob blocks and extracts their cache_scope and depends_on
    from BlockMetadata. Target IDs resolve through the oob_registry when
    available, falling back to the ``block_name.removesuffix("_oob")`` convention.
    When template_metadata is unavailable and a registry is present, registered
    blocks are used as the fallback set.
    """
    meta = adapter.template_metadata(template_name)
    oob_blocks: list[OOBBlockInfo] = []

    if meta is not None:
        blocks = getattr(meta, "blocks", None) or {}
        for block_name, block_meta in blocks.items():
            if not block_name.endswith(OOB_BLOCK_SUFFIX):
                continue
            if oob_registry is not None:
                target_id = oob_registry.resolve_target(block_name)
            else:
                target_id = block_name.removesuffix(OOB_BLOCK_SUFFIX)
            oob_blocks.append(
                OOBBlockInfo(
                    block_name=block_name,
                    target_id=target_id,
                    cache_scope=getattr(block_meta, "cache_scope", "unknown"),
                    depends_on=frozenset(getattr(block_meta, "depends_on", ())),
                )
            )
    elif oob_registry is not None:
        # Fallback when template metadata is unavailable (e.g. Jinja2 adapter).
        # Only include registry blocks we can verify exist via the adapter;
        # without metadata we cannot confirm the block is renderable, so we
        # skip rather than producing a contract with phantom blocks that
        # cause render_block failures downstream.
        _log.debug(
            "build_layout_contract: no metadata for %r, skipping registry blocks",
            template_name,
        )

    return LayoutContract(template_name=template_name, oob_blocks=tuple(oob_blocks))


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
    oob_registry: OOBRegistry | None = None,
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
        per_layout_oob: dict[str, set[str]] = {}
        if plan.intent == "full_page":
            registry_blocks = set(oob_registry.registered_blocks) if oob_registry else set()
            for layout_info in layouts:
                own_oob = _oob_block_names(adapter, layout_info.template_name)
                # Registry blocks (e.g. shell_actions_oob) only suppressed
                # when the layout actually defines them.
                meta = adapter.template_metadata(layout_info.template_name)
                all_blocks = set(getattr(meta, "blocks", None) or ()) if meta else set()
                per_layout_oob[layout_info.template_name] = own_oob | (registry_blocks & all_blocks)
        for layout_info in reversed(layouts):
            block_overrides: dict[str, str] = {"content": main_html}
            if plan.intent == "full_page":
                for name in per_layout_oob.get(layout_info.template_name, set()):
                    block_overrides[name] = ""
            main_html = adapter.compose_layout(
                layout_info.template_name,
                block_overrides,
                plan.layout_context,
            )

    # Augment region_updates with shell OOB blocks discovered via AST
    region_updates_list: list[RegionUpdate] = list(plan.region_updates)
    if plan.include_layout_oob and plan.layout_chain and plan.layout_chain.layouts:
        layout_ctx = plan.layout_context
        # Nested filesystem layouts (e.g. marketing root + section app shell) each
        # define *_oob regions. Deepest layout wins per target_id so section
        # sidebars/breadcrumbs refresh on boosted navigation, not only root OOB.
        #
        # Scoped OOB: when oob_scope is set, only include OOB from layouts at
        # or above the matched scope's depth (the scope's layout + ancestors).
        # When oob_scope is None (boosted nav), include all layouts.
        max_oob_depth: int | None = None
        if plan.oob_scope is not None:
            for li in plan.layout_chain.layouts:
                scope = getattr(li, "swap_scope_name", None)
                if scope == plan.oob_scope:
                    max_oob_depth = li.depth
                    break

        seen_oob_targets: set[str] = set()
        for layout_info in reversed(plan.layout_chain.layouts):
            if max_oob_depth is not None and layout_info.depth > max_oob_depth:
                continue
            if oob_registry is not None:
                contract = oob_registry.get_or_build_contract(adapter, layout_info.template_name)
            else:
                contract = build_layout_contract(adapter, layout_info.template_name)

            for oob in contract.oob_blocks:
                if oob.cache_scope == "site" and not oob.depends_on:
                    continue
                if "page_title" in oob.depends_on and "page_title" not in layout_ctx:
                    continue
                if oob.target_id in seen_oob_targets:
                    continue
                seen_oob_targets.add(oob.target_id)
                region_updates_list.append(
                    RegionUpdate(
                        region=oob.target_id,
                        view=ViewRef(
                            template=layout_info.template_name,
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
                _log.error(
                    "RenderPlan: block %r in %r failed to render",
                    ru.view.block,
                    ru.view.template,
                    exc_info=True,
                )
                html = ""
        else:
            html = ""
        region_htmls[ru.region] = html

    return RenderedPlan(main_html=main_html, region_htmls=region_htmls)


def serialize_rendered_plan(
    rendered: RenderedPlan,
    *,
    oob_registry: OOBRegistry | None = None,
) -> str:
    """Serialize rendered plan to final HTML with OOB fragments."""
    parts: list[str] = [rendered.main_html]
    for region_id, html in rendered.region_htmls.items():
        if oob_registry is not None:
            swap, wrap = oob_registry.resolve_serialization(region_id)
        elif region_id == SHELL_ACTIONS_TARGET:
            swap, wrap = "innerHTML", True
        else:
            swap, wrap = "true", True
        if wrap:
            parts.append(f'<div id="{region_id}" hx-swap-oob="{swap}">{html}</div>')
        else:
            parts.append(html)
    return "\n".join(parts)
