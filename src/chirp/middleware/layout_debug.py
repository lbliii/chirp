"""Layout chain debug middleware — adds X-Chirp-Layout-* headers in debug mode.

When config.debug is True, this middleware adds response headers showing
the layout chain resolution for LayoutPage responses. Helps diagnose
nested shell targeting during development.
"""

from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next

_CACHE_KEY = "_layout_debug"


def set_layout_debug_metadata(request: Request | None, chain: str, match: str, mode: str) -> None:
    """Store layout chain metadata on the request for the layout debug middleware."""
    if request is not None:
        request._cache[_CACHE_KEY] = {"chain": chain, "match": match, "mode": mode}


class LayoutDebugMiddleware:
    """Middleware that adds X-Chirp-Layout-* headers when config.debug is True."""

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        metadata = request._cache.pop(_CACHE_KEY, None)
        if metadata is None:
            return response

        for name, value in metadata.items():
            header = f"X-Chirp-Layout-{name.capitalize()}"
            response = response.with_header(header, value)

        return response
