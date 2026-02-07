"""ASGI handler — translates ASGI scope/messages to chirp types.

The only component that touches raw ASGI directly. Converts scope dicts
to typed Request objects, dispatches through middleware and routing,
and sends Response back through ASGI send().
"""

import inspect
from collections.abc import Callable
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import Next
from chirp.routing.route import RouteMatch
from chirp.routing.router import Router
from chirp.server.negotiation import negotiate


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

    try:
        # Build the innermost handler (router dispatch)
        async def dispatch(request: Request) -> Response:
            match = router.match(request.method, request.path)
            return await _invoke_handler(match, request, kida_env=kida_env)

        # Wrap middleware around the dispatch
        handler: Next = dispatch
        for mw in reversed(middleware):
            outer = handler
            mw_ref = mw

            async def make_next(req: Request, _mw: Any = mw_ref, _next: Next = outer) -> Response:
                return await _mw(req, _next)

            handler = make_next

        # Build Request from ASGI scope
        request = Request.from_asgi(scope, receive)

        # Execute the full pipeline
        response = await handler(request)

    except HTTPError as exc:
        response = _handle_http_error(exc, error_handlers, kida_env, debug)
    except Exception as exc:
        response = _handle_internal_error(exc, error_handlers, kida_env, debug)

    await _send_response(response, send)


async def _invoke_handler(
    match: RouteMatch,
    request: Request,
    *,
    kida_env: Environment | None = None,
) -> Response:
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


def _handle_http_error(
    exc: HTTPError,
    error_handlers: dict[int | type, Callable[..., Any]],
    kida_env: Environment | None,
    debug: bool,
) -> Response:
    """Map an HTTPError to a Response using registered error handlers."""
    # Try exact exception type
    handler = error_handlers.get(type(exc))
    if handler is None:
        # Try status code
        handler = error_handlers.get(exc.status)
    if handler is not None:
        # Error handlers return values just like route handlers
        result = handler()
        if isinstance(result, Response):
            return result
        return negotiate(result, kida_env=kida_env)

    # Default error response
    body = exc.detail or f"Error {exc.status}"
    if debug and exc.detail:
        body = f"{exc.status}: {exc.detail}"

    resp = Response(body=body).with_status(exc.status)
    for name, value in exc.headers:
        resp = resp.with_header(name, value)
    return resp


def _handle_internal_error(
    exc: Exception,
    error_handlers: dict[int | type, Callable[..., Any]],
    kida_env: Environment | None,
    debug: bool,
) -> Response:
    """Handle unexpected exceptions as 500 errors."""
    handler = error_handlers.get(500) or error_handlers.get(type(exc))
    if handler is not None:
        result = handler()
        if isinstance(result, Response):
            return result
        return negotiate(result, kida_env=kida_env)

    if debug:
        import traceback

        tb = traceback.format_exc()
        return Response(body=f"<pre>{tb}</pre>", status=500)

    return Response(body="Internal Server Error", status=500)


async def _send_response(response: Response, send: Send) -> None:
    """Translate a chirp Response into ASGI send() calls."""
    # Build raw headers
    raw_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", response.content_type.encode("latin-1")),
    ]
    for name, value in response.headers:
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    raw_headers.extend(
        (b"set-cookie", cookie.to_header_value().encode("latin-1"))
        for cookie in response.cookies
    )

    body = response.body_bytes

    raw_headers.append((b"content-length", str(len(body)).encode("latin-1")))

    await send({
        "type": "http.response.start",
        "status": response.status,
        "headers": raw_headers,
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })
