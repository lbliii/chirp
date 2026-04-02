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
from chirp.server.debug.render_plan_snapshot import RENDER_DEBUG_CACHE_KEY

_CACHE_KEY = "_layout_debug"
_ROUTE_CACHE_KEY = "_route_debug"


def set_layout_debug_metadata(request: Request | None, chain: str, match: str, mode: str) -> None:
    """Store layout chain metadata on the request for the layout debug middleware."""
    if request is not None:
        request._cache[_CACHE_KEY] = {"chain": chain, "match": match, "mode": mode}


def _compact_render_plan(plan: dict) -> dict:
    """Trim a render plan snapshot to header-safe size (~2 KB)."""
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

        render_plan = request._cache.pop(RENDER_DEBUG_CACHE_KEY, None)
        if render_plan is not None:
            try:
                compact = _compact_render_plan(render_plan)
                encoded = base64.b64encode(json.dumps(compact, separators=(",", ":")).encode())
                response = response.with_header("X-Chirp-Render-Plan", encoded.decode("ascii"))
            except Exception:  # noqa: S110
                pass

        return response
