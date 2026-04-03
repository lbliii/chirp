"""Serialize RenderPlan for dev-mode debug HTML (repr previews, bounded size).

Also provides :func:`get_render_plan` for public read-only access to the
frozen ``RenderPlan`` that was used to render the current request.
"""

from __future__ import annotations

from typing import Any

from chirp.http.request import Request
from chirp.templating.render_plan import RenderPlan

RENDER_DEBUG_CACHE_KEY = "_chirp_render_debug"
RENDER_PLAN_CACHE_KEY = "_chirp_render_plan"

_MAX_CONTEXT_KEYS = 48
_MAX_REPR_LEN = 120


def _preview_value(value: Any) -> str:
    try:
        s = repr(value)
    except Exception as exc:
        return f"<repr failed: {type(exc).__name__}>"
    if len(s) > _MAX_REPR_LEN:
        return f"{s[: _MAX_REPR_LEN - 3]}..."
    return s


def summarize_context_for_debug(ctx: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (key, repr preview) pairs for debug display."""
    items: list[tuple[str, str]] = []
    for i, (key, val) in enumerate(ctx.items()):
        if i >= _MAX_CONTEXT_KEYS:
            omitted = len(ctx) - _MAX_CONTEXT_KEYS
            items.append(("…", f"({omitted} more keys omitted)"))
            break
        items.append((str(key), _preview_value(val)))
    return items


def serialize_render_plan_for_debug(plan: RenderPlan) -> dict[str, Any]:
    """Build a snapshot dict for the debug error page."""
    lc = plan.layout_chain
    chain_layouts: list[dict[str, Any]] = []
    if lc is not None:
        chain_layouts.extend(
            {
                "template_name": lay.template_name,
                "target": lay.target,
                "depth": lay.depth,
            }
            for lay in lc.layouts
        )

    applied_names: list[str] = (
        [lay.template_name for lay in lc.layouts[plan.layout_start_index :]]
        if lc is not None and plan.layout_start_index < len(lc.layouts)
        else []
    )

    regions = [
        {
            "region": ru.region,
            "template": ru.view.template,
            "block": ru.view.block,
            "mode": ru.mode,
        }
        for ru in plan.region_updates
    ]

    return {
        "intent": plan.intent,
        "render_full_template": plan.render_full_template,
        "apply_layouts": plan.apply_layouts,
        "layout_start_index": plan.layout_start_index,
        "include_layout_oob": plan.include_layout_oob,
        "main_view": {
            "template": plan.main_view.template,
            "block": plan.main_view.block,
            "context_keys": list(plan.main_view.context.keys()),
            "context_preview": summarize_context_for_debug(plan.main_view.context),
        },
        "layout_chain": chain_layouts,
        "layouts_applied": applied_names,
        "layout_context_preview": summarize_context_for_debug(plan.layout_context),
        "region_updates": regions,
    }


def stash_render_debug_for_request(
    plan: RenderPlan,
    request: Request | None,
    *,
    debug: bool = False,
) -> None:
    """Store render plan on the request for middleware and debug tools.

    The frozen ``RenderPlan`` object is always stashed (zero overhead —
    it is already immutable).  The heavier serialized debug snapshot is
    only built when *debug* is True.
    """
    if request is None:
        return
    request._cache[RENDER_PLAN_CACHE_KEY] = plan
    if debug:
        request._cache[RENDER_DEBUG_CACHE_KEY] = serialize_render_plan_for_debug(plan)


def get_render_plan(request: Any) -> RenderPlan | None:
    """Return the frozen ``RenderPlan`` used to render this request.

    Available after content negotiation has run for ``Page``,
    ``LayoutPage``, or ``PageComposition`` return types.  Returns
    ``None`` for non-page responses or if negotiation has not yet run.

    Use in middleware to inspect rendering decisions::

        plan = get_render_plan(request)
        if plan is not None:
            print(plan.intent)  # "full_page", "page_fragment", "local_fragment"
    """
    cache = getattr(request, "_cache", None)
    if not isinstance(cache, dict):
        return None
    plan = cache.get(RENDER_PLAN_CACHE_KEY)
    return plan if isinstance(plan, RenderPlan) else None


def read_render_debug_from_request(request: Any) -> dict[str, Any] | None:
    """Return stashed snapshot if present (request may be a test double)."""
    cache = getattr(request, "_cache", None)
    if not isinstance(cache, dict):
        return None
    raw = cache.get(RENDER_DEBUG_CACHE_KEY)
    return raw if isinstance(raw, dict) else None
