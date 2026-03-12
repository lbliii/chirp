"""Layout chain and route contract debug middleware.

When config.debug is True, adds X-Chirp-Layout-* and X-Chirp-Route-* headers
to help diagnose layout resolution and route contract metadata.
"""

from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next

_CACHE_KEY = "_layout_debug"
_ROUTE_CACHE_KEY = "_route_debug"


def set_layout_debug_metadata(request: Request | None, chain: str, match: str, mode: str) -> None:
    """Store layout chain metadata on the request for the layout debug middleware."""
    if request is not None:
        request._cache[_CACHE_KEY] = {"chain": chain, "match": match, "mode": mode}


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

        return response
