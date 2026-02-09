"""Error handling pipeline for chirp requests.

Maps HTTPError exceptions and unexpected failures to appropriate
Response objects, using registered error handlers or sensible defaults.
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any

from kida import Environment

from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.server.negotiation import negotiate

logger = logging.getLogger("chirp.server")


def default_fragment_error(status: int, detail: str) -> str:
    """Minimal HTML snippet for fragment error responses."""
    return f'<div class="chirp-error" data-status="{status}">{detail}</div>'


def _with_htmx_error_headers(response: Response, request: Request) -> Response:
    """Add htmx error-handling headers when the request is a fragment.

    Headers added:
    - ``HX-Retarget: #chirp-error`` — redirect error content to a dedicated container
    - ``HX-Reswap: innerHTML`` — replace (not append) the error content
    - ``HX-Trigger: chirpError`` — fire a client-side event for custom handling
    """
    if not request.is_fragment:
        return response
    return (
        response
        .with_header("HX-Retarget", "#chirp-error")
        .with_header("HX-Reswap", "innerHTML")
        .with_header("HX-Trigger", "chirpError")
    )


async def call_error_handler(
    handler: Callable[..., Any],
    request: Request,
    exc: Exception,
    kida_env: Environment | None,
) -> Response:
    """Invoke a user-registered error handler with introspected arguments.

    Error handlers may accept zero, one (request), or two (request, exc) args.
    Supports both sync and async error handlers.
    """
    sig = inspect.signature(handler)
    params = list(sig.parameters.values())

    if len(params) >= 2:
        result = handler(request, exc)
    elif len(params) == 1:
        result = handler(request)
    else:
        result = handler()

    if inspect.isawaitable(result):
        result = await result

    if isinstance(result, Response):
        return result
    return negotiate(result, kida_env=kida_env)


async def handle_http_error(
    exc: HTTPError,
    request: Request,
    error_handlers: dict[int | type, Callable[..., Any]],
    kida_env: Environment | None,
    debug: bool,
) -> Response:
    """Map an HTTPError to a Response using registered error handlers."""
    logger.debug("%d %s %s — %s", exc.status, request.method, request.path, exc.detail)

    # Try exact exception type, then status code
    handler = error_handlers.get(type(exc)) or error_handlers.get(exc.status)
    if handler is not None:
        response = await call_error_handler(handler, request, exc, kida_env)
        # Preserve the HTTP status from the exception unless the handler
        # explicitly returned a Response with its own status
        if response.status == 200:
            response = response.with_status(exc.status)
        return response

    # Default error response
    detail = exc.detail or f"Error {exc.status}"
    if debug and exc.detail:
        detail = f"{exc.status}: {exc.detail}"

    # Fragment-aware: return a snippet instead of a full page
    body = default_fragment_error(exc.status, detail) if request.is_fragment else detail

    resp = Response(body=body).with_status(exc.status)
    for name, value in exc.headers:
        resp = resp.with_header(name, value)
    return _with_htmx_error_headers(resp, request)


async def handle_internal_error(
    exc: Exception,
    request: Request,
    error_handlers: dict[int | type, Callable[..., Any]],
    kida_env: Environment | None,
    debug: bool,
) -> Response:
    """Handle unexpected exceptions as 500 errors."""
    logger.exception("500 %s %s", request.method, request.path)

    handler = error_handlers.get(500) or error_handlers.get(type(exc))
    if handler is not None:
        return await call_error_handler(handler, request, exc, kida_env)

    if debug:
        from chirp.server.debug_page import render_debug_page

        body = render_debug_page(exc, request, is_fragment=request.is_fragment)
        return _with_htmx_error_headers(Response(body=body, status=500), request)

    if request.is_fragment:
        resp = Response(body=default_fragment_error(500, "Internal Server Error"), status=500)
        return _with_htmx_error_headers(resp, request)

    return Response(body="Internal Server Error", status=500)
