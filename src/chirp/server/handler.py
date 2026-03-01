"""ASGI handler — translates ASGI scope/messages to chirp types.

The only component that touches raw ASGI directly. Converts scope dicts
to typed Request objects, dispatches through middleware and routing,
and sends Response back through ASGI send().
"""

import inspect
from collections.abc import Callable
from contextvars import Token
from dataclasses import replace
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp._internal.invoke import invoke
from chirp.context import g, request_var
from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response, SSEResponse, StreamingResponse
from chirp.middleware.protocol import AnyResponse, Next
from chirp.routing.route import RouteMatch
from chirp.routing.router import Router
from chirp.server.errors import handle_http_error, handle_internal_error
from chirp.server.htmx_debug import HTMX_DEBUG_BOOT_JS, HTMX_DEBUG_BOOT_PATH
from chirp.server.negotiation import negotiate
from chirp.server.sender import send_response, send_streaming_response
from chirp.tools.registry import ToolRegistry


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
    providers: dict[type, Callable[..., Any]] | None = None,
    tool_registry: ToolRegistry | None = None,
    mcp_path: str = "/mcp",
    sse_heartbeat_interval: float = 15.0,
    sse_retry_ms: int | None = None,
    sse_close_event: str | None = None,
    db: Any = None,
) -> None:
    """Process a single HTTP request through the full pipeline."""
    if scope["type"] != "http":
        return

    # Build Request from ASGI scope
    request = Request.from_asgi(scope, receive)

    # Set request context var (reset after dispatch)
    token: Token[Request] = request_var.set(request)

    # Set database context var per-request (lifespan sets it only in its task)
    db_token: Token[Any] | None = None
    if db is not None:
        from chirp.data.database import _db_var

        db_token = _db_var.set(db)

    try:
        # Build the innermost handler (router dispatch + MCP)
        async def dispatch(req: Request) -> AnyResponse:
            # Built-in debug helper asset; loaded once per full page.
            if debug and req.path == HTMX_DEBUG_BOOT_PATH:
                return Response(
                    body=HTMX_DEBUG_BOOT_JS,
                    content_type="application/javascript; charset=utf-8",
                    render_intent="full_page",
                )

            # MCP endpoint — dispatched inside middleware so auth/CORS apply
            if tool_registry is not None and len(tool_registry) > 0 and req.path == mcp_path:
                from chirp.tools.handler import handle_mcp_request

                return await handle_mcp_request(req, tool_registry)

            match = router.match(req.method, req.path)
            return await _invoke_handler(
                match,
                req,
                kida_env=kida_env,
                providers=providers,
            )

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
        if db_token is not None:
            from chirp.data.database import _db_var

            _db_var.reset(db_token)
        g._reset()
        request_var.reset(token)

    # Dispatch based on response type
    if isinstance(response, SSEResponse):
        from chirp.realtime.sse import handle_sse

        stream = response.event_stream
        if stream.heartbeat_interval == 15.0:
            stream = replace(stream, heartbeat_interval=sse_heartbeat_interval)

        await handle_sse(
            stream,
            send,
            receive,
            kida_env=response.kida_env,
            debug=debug,
            retry_ms=sse_retry_ms,
            close_event=sse_close_event,
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
    providers: dict[type, Callable[..., Any]] | None = None,
) -> AnyResponse:
    """Call the matched route handler, converting path params and return value."""
    handler = match.route.handler

    # Inject Request into the updated request with path_params
    # Carry over _cache so body/form data parsed by middleware isn't lost
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
        _cache=request._cache,
    )

    # Pre-read body data if any handler param needs typed extraction
    body_data = await _read_body_if_needed(handler, request)

    # Build kwargs from handler signature
    kwargs = _build_handler_kwargs(
        handler,
        request,
        match.path_params,
        providers,
        body_data=body_data,
    )

    # Call the handler (sync or async — invoke() handles both)
    result = await invoke(handler, **kwargs)

    return negotiate(result, kida_env=kida_env, request=request)


def _build_handler_kwargs(
    handler: Callable[..., Any],
    request: Request,
    path_params: dict[str, str],
    providers: dict[type, Callable[..., Any]] | None = None,
    *,
    body_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect handler signature and build kwargs from request + path params.

    Resolution order:
    1. ``request`` parameter (by name or ``Request`` annotation)
    2. Path parameters (by name, with type conversion)
    3. Context cascade values (page routes only — handled in page_wrapper)
    4. Service providers (by type annotation via ``app.provide()``)
    5. Typed extraction (dataclass annotation → query string or body)
    """
    from chirp.extraction import extract_dataclass, is_extractable_dataclass

    sig = inspect.signature(handler, eval_str=True)
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
        elif (
            providers
            and param.annotation is not inspect.Parameter.empty
            and param.annotation in providers
        ):
            kwargs[name] = providers[param.annotation]()
        elif param.annotation is not inspect.Parameter.empty and is_extractable_dataclass(
            param.annotation
        ):
            # Typed extraction: GET → query, POST/PUT/PATCH → body
            if request.method in ("GET", "HEAD"):
                kwargs[name] = extract_dataclass(param.annotation, request.query)
            elif body_data is not None:
                kwargs[name] = extract_dataclass(param.annotation, body_data)

    return kwargs


async def _read_body_if_needed(
    handler: Callable[..., Any],
    request: Request,
) -> dict[str, Any] | None:
    """Pre-read form/JSON body if the handler has extractable dataclass params.

    Only reads the body for non-GET methods.  Returns ``None`` if no
    extraction is needed or the method is GET/HEAD.
    """
    if request.method in ("GET", "HEAD"):
        return None

    from chirp.extraction import is_extractable_dataclass

    sig = inspect.signature(handler, eval_str=True)
    needs_extraction = any(
        param.annotation is not inspect.Parameter.empty
        and is_extractable_dataclass(param.annotation)
        for param in sig.parameters.values()
    )

    if not needs_extraction:
        return None

    ct = request.content_type or ""
    if "json" in ct:
        return await request.json()
    return dict(await request.form())
