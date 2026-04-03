"""Layout chain and route contract debug middleware.

When config.debug is True, adds X-Chirp-Layout-* and X-Chirp-Route-* headers
to help diagnose layout resolution and route contract metadata.

Also emits ``X-Chirp-Render-Plan`` with a base64-encoded compact JSON snapshot
of the render plan for consumption by the HTMX debug tray.
"""

import base64
import json

from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next
from chirp.server.debug.render_plan_snapshot import (
    RENDER_DEBUG_CACHE_KEY,
    get_render_plan,
)

_CACHE_KEY = "_layout_debug"
_ROUTE_CACHE_KEY = "_route_debug"


def set_layout_debug_metadata(request: Request | None, chain: str, match: str, mode: str) -> None:
    """Store layout chain metadata on the request for the layout debug middleware."""
    if request is not None:
        request._cache[_CACHE_KEY] = {"chain": chain, "match": match, "mode": mode}


def _build_render_plan_payload(request: Request) -> dict | None:
    """Build a rich render plan payload from the stashed RenderPlan.

    Uses the public ``get_render_plan()`` API to access the frozen
    RenderPlan object, producing a richer payload than the old compact
    snapshot (which was capped at 20 context keys and ~2 KB).
    """
    plan = get_render_plan(request)
    if plan is None:
        return None

    mv = plan.main_view
    context_entries = []
    for key, val in mv.context.items():
        type_name = type(val).__name__
        context_entries.append({"key": key, "type": type_name})

    layout_chain_info = [
        {"template": lay.template_name, "target": lay.target, "depth": lay.depth}
        for lay in (plan.layout_chain.layouts if plan.layout_chain is not None else ())
    ]

    layouts_applied = []
    if plan.layout_chain is not None and plan.layout_start_index < len(plan.layout_chain.layouts):
        layouts_applied = [
            lay.template_name for lay in plan.layout_chain.layouts[plan.layout_start_index :]
        ]

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
        "template": mv.template,
        "block": mv.block,
        "render_full_template": plan.render_full_template,
        "apply_layouts": plan.apply_layouts,
        "context": context_entries,
        "layout_chain": layout_chain_info,
        "layouts_applied": layouts_applied,
        "layout_start": plan.layout_start_index,
        "regions": regions,
        "include_layout_oob": plan.include_layout_oob,
    }


def _compact_render_plan(plan: dict) -> dict:
    """Trim a render plan snapshot to header-safe size (~2 KB).

    Fallback used when the frozen RenderPlan is not available.
    """
    mv = plan.get("main_view", {})
    return {
        "intent": plan.get("intent"),
        "template": mv.get("template"),
        "block": mv.get("block"),
        "context_keys": mv.get("context_keys", [])[:20],
        "layouts_applied": plan.get("layouts_applied", []),
        "layout_start": plan.get("layout_start_index", 0),
        "regions": plan.get("region_updates", []),
        "include_layout_oob": plan.get("include_layout_oob", False),
    }


class LayoutDebugMiddleware:
    """Middleware that adds X-Chirp-Layout-* and X-Chirp-Route-* headers when config.debug."""

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        metadata = request._cache.pop(_CACHE_KEY, None)
        if metadata is not None:
            for name, value in metadata.items():
                header = f"X-Chirp-Layout-{name.capitalize()}"
                response = response.with_header(header, value)

        route_info = request._cache.pop(_ROUTE_CACHE_KEY, None)
        if route_info is not None:
            response = response.with_header("X-Chirp-Route-Kind", route_info.route_kind)
            response = response.with_header("X-Chirp-Route-Files", route_info.route_files)
            response = response.with_header("X-Chirp-Route-Meta", route_info.route_meta)
            response = response.with_header("X-Chirp-Route-Section", route_info.route_section)
            response = response.with_header("X-Chirp-Context-Chain", route_info.context_chain)
            response = response.with_header("X-Chirp-Shell-Context", route_info.shell_context_keys)

        # Build render plan payload — prefer the rich version from the frozen
        # RenderPlan object, fall back to the serialized debug snapshot.
        try:
            payload = _build_render_plan_payload(request)
            if payload is None:
                debug_snapshot = request._cache.pop(RENDER_DEBUG_CACHE_KEY, None)
                if debug_snapshot is not None:
                    payload = _compact_render_plan(debug_snapshot)
            else:
                request._cache.pop(RENDER_DEBUG_CACHE_KEY, None)
            if payload is not None:
                encoded = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode())
                response = response.with_header("X-Chirp-Render-Plan", encoded.decode("ascii"))
        except Exception:  # noqa: S110
            pass

        return response
