"""ASGI handler — translates ASGI scope/messages to chirp types.

The only component that touches raw ASGI directly. Converts scope dicts
to typed Request objects, dispatches through middleware and routing,
and sends Response back through ASGI send().
"""

import inspect
from collections.abc import Callable
from contextvars import Token
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp.context import g, request_var
from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response, SSEResponse, StreamingResponse
from chirp.middleware.protocol import AnyResponse
from chirp.routing.route import RouteMatch
from chirp.routing.router import Router
from chirp.server.errors import handle_http_error, handle_internal_error
from chirp.server.negotiation import negotiate
from chirp.server.sender import send_response, send_streaming_response


async def handle_request(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    router: Router,
    middleware: tuple[Callable[..., Any], ...],
    error_handlers: dict[int | type, Callable[..., Any]],
    kida_env: Environment | None = None,
    debug: bool,
) -> None:
    """Process a single HTTP request through the full pipeline."""
    if scope["type"] != "http":
        return

    # Build Request from ASGI scope
    request = Request.from_asgi(scope, receive)

    # Set request context var (reset after dispatch)
    token: Token[Request] = request_var.set(request)

    try:
        # Build the innermost handler (router dispatch)
        async def dispatch(req: Request) -> AnyResponse:
            match = router.match(req.method, req.path)
            return await _invoke_handler(match, req, kida_env=kida_env)

        # Wrap middleware around the dispatch
        handler = dispatch
        for mw in reversed(middleware):
            outer = handler
            mw_ref = mw

            async def make_next(req: Request, _mw: Any = mw_ref, _next: Next = outer) -> Response:
                return await _mw(req, _next)

            handler = make_next

        # Execute the full pipeline
        response = await handler(request)

    except HTTPError as exc:
        response = await handle_http_error(exc, request, error_handlers, kida_env, debug)
    except Exception as exc:
        response = await handle_internal_error(exc, request, error_handlers, kida_env, debug)
    finally:
        g._reset()
        request_var.reset(token)

    # Dispatch based on response type
    if isinstance(response, SSEResponse):
        from chirp.realtime.sse import handle_sse

        await handle_sse(
            response.event_stream,
            send,
            receive,
            kida_env=response.kida_env,
        )
    elif isinstance(response, StreamingResponse):
        await send_streaming_response(response, send, debug=debug)
    else:
        await send_response(response, send)


async def _invoke_handler(
    match: RouteMatch,
    request: Request,
    *,
    kida_env: Environment | None = None,
) -> AnyResponse:
    """Call the matched route handler, converting path params and return value."""
    handler = match.route.handler

    # Inject Request into the updated request with path_params
    request = Request(
        method=request.method,
        path=request.path,
        headers=request.headers,
        query=request.query,
        path_params=match.path_params,
        http_version=request.http_version,
        server=request.server,
        client=request.client,
        cookies=request.cookies,
        _receive=request._receive,
    )

    # Build kwargs from handler signature
    kwargs = _build_handler_kwargs(handler, request, match.path_params)

    # Call the handler
    result = handler(**kwargs)
    if inspect.isawaitable(result):
        result = await result

    return negotiate(result, kida_env=kida_env)


def _build_handler_kwargs(
    handler: Callable[..., Any],
    request: Request,
    path_params: dict[str, str],
) -> dict[str, Any]:
    """Inspect handler signature and build kwargs from request + path params."""
    sig = inspect.signature(handler)
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name == "request" or param.annotation is Request:
            kwargs[name] = request
        elif name in path_params:
            # Convert path param to annotated type if possible
            value = path_params[name]
            if param.annotation is not inspect.Parameter.empty:
                try:
                    kwargs[name] = param.annotation(value)
                except (ValueError, TypeError):
                    kwargs[name] = value
            else:
                kwargs[name] = value

    return kwargs
