"""ASGI handler — translates ASGI scope/messages to chirp types.

The only component that touches raw ASGI directly. Converts scope dicts
to typed Request objects, dispatches through middleware and routing,
and sends Response back through ASGI send().
"""

from collections.abc import Callable
from contextvars import Token
from dataclasses import replace
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp._internal.invoke import invoke
from chirp._internal.invoke_plan import InvokePlan
from chirp.context import force_inline_sync_var, g, request_var
from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response, SSEResponse, StreamingResponse
from chirp.logging import request_id_var
from chirp.middleware.protocol import AnyResponse, Next
from chirp.routing.route import RouteMatch
from chirp.routing.router import Router
from chirp.server.errors import handle_http_error, handle_internal_error
from chirp.server.htmx_debug import HTMX_DEBUG_BOOT_JS, HTMX_DEBUG_BOOT_PATH
from chirp.server.negotiation import negotiate
from chirp.server.route_explorer import ROUTE_EXPLORER_PATH, render_route_explorer
from chirp.server.sender import send_response, send_streaming_response
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.oob_registry import OOBRegistry
from chirp.tools.registry import ToolRegistry


def compile_middleware_chain(
    middleware: tuple[Callable[..., Any], ...],
    dispatch: Callable[[Request], Any],
) -> Callable[[Request], Any]:
    """Build middleware chain once. Returns async handler(req) -> Response."""
    chain = dispatch
    for mw in reversed(middleware):
        inner = chain
        mw_ref = mw

        async def layer(req: Request, _mw: Any = mw_ref, _next: Next = inner) -> AnyResponse:
            return await _mw(req, _next)

        chain = layer
    return chain


def create_request_handler(
    *,
    router: Router,
    middleware: tuple[Callable[..., Any], ...],
    tool_registry: ToolRegistry | None,
    mcp_path: str,
    debug: bool,
    providers: dict[type, Callable[..., Any]] | None,
    kida_env: Environment | None,
    oob_registry: OOBRegistry | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    discovered_routes: list[Any] | None = None,
) -> Callable[[Request], Any]:
    """Build the full middleware + dispatch chain once. Reuse per request."""
    routes = discovered_routes or []

    async def dispatch(req: Request) -> AnyResponse:
        if debug and req.path == HTMX_DEBUG_BOOT_PATH:
            return Response(
                body=HTMX_DEBUG_BOOT_JS,
                content_type="application/javascript; charset=utf-8",
                render_intent="full_page",
            )
        if req.path == ROUTE_EXPLORER_PATH:
            if debug:
                path_filter = req.query.get("path", "")
                html_body = render_route_explorer(routes, path_filter=path_filter or None)
                return Response(
                    body=html_body,
                    content_type="text/html; charset=utf-8",
                    render_intent="full_page",
                )
            from chirp.errors import NotFound

            raise NotFound()
        if tool_registry is not None and len(tool_registry) > 0 and req.path == mcp_path:
            from chirp.tools.handler import handle_mcp_request

            return await handle_mcp_request(req, tool_registry)
        match = router.match(req.method, req.path)
        return await _invoke_handler(
            match,
            req,
            kida_env=kida_env,
            providers=providers,
            validate_blocks=debug,
            force_inline_sync=force_inline_sync_var.get(),
            oob_registry=oob_registry,
            fragment_target_registry=fragment_target_registry,
        )

    return compile_middleware_chain(middleware, dispatch)


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
    compiled_handler: Callable[[Request], Any] | None = None,
    oob_registry: OOBRegistry | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
) -> None:
    """Process a single HTTP request through the full pipeline."""
    if scope["type"] != "http":
        return

    # Build Request from ASGI scope
    request = Request.from_asgi(scope, receive)

    # Pounce sync workers set this so sync handlers run directly on the
    # worker thread instead of being dispatched through asyncio.to_thread().
    extensions = scope.get("extensions") or {}
    force_inline_sync = bool(extensions.get("pounce.inline_sync"))

    # Set request and request_id context vars (reset after dispatch)
    token: Token[Request] = request_var.set(request)
    rid_token = request_id_var.set(request.request_id)
    sync_token = force_inline_sync_var.set(force_inline_sync)

    try:
        # Use pre-compiled chain or build per request
        if compiled_handler is not None:
            handler = compiled_handler
        else:

            async def dispatch(req: Request) -> AnyResponse:
                if debug and req.path == HTMX_DEBUG_BOOT_PATH:
                    return Response(
                        body=HTMX_DEBUG_BOOT_JS,
                        content_type="application/javascript; charset=utf-8",
                        render_intent="full_page",
                    )
                if tool_registry is not None and len(tool_registry) > 0 and req.path == mcp_path:
                    from chirp.tools.handler import handle_mcp_request

                    return await handle_mcp_request(req, tool_registry)
                match = router.match(req.method, req.path)
                return await _invoke_handler(
                    match,
                    req,
                    kida_env=kida_env,
                    providers=providers,
                    validate_blocks=debug,
                    force_inline_sync=force_inline_sync_var.get(),
                    oob_registry=oob_registry,
                    fragment_target_registry=fragment_target_registry,
                )

            handler = compile_middleware_chain(middleware, dispatch)

        # Execute the full pipeline
        response = await handler(request)

    except HTTPError as exc:
        response = await handle_http_error(
            exc,
            request,
            error_handlers,
            kida_env,
            debug,
            oob_registry=oob_registry,
            fragment_target_registry=fragment_target_registry,
        )
    except Exception as exc:
        response = await handle_internal_error(
            exc,
            request,
            error_handlers,
            kida_env,
            debug,
            oob_registry=oob_registry,
            fragment_target_registry=fragment_target_registry,
        )
    finally:
        g._reset()
        request_var.reset(token)
        request_id_var.reset(rid_token)
        force_inline_sync_var.reset(sync_token)

    # Dispatch based on response type — X-Request-ID injected at send time
    # to avoid an extra Response clone + tuple allocation per request.
    rid = request.request_id
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
        await send_streaming_response(response, send, debug=debug, request_id=rid)
    else:
        await send_response(response, send, request_id=rid)


async def _invoke_handler(
    match: RouteMatch,
    request: Request,
    *,
    kida_env: Environment | None = None,
    providers: dict[type, Callable[..., Any]] | None = None,
    validate_blocks: bool = False,
    force_inline_sync: bool = False,
    oob_registry: OOBRegistry | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
) -> AnyResponse:
    """Call the matched route handler, converting path params and return value."""
    handler = match.route.handler

    # Inject path_params into Request; skip clone when already identical
    if request.path_params != match.path_params:
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
            request_id=request.request_id,
            _receive=request._receive,
            _cache=request._cache,
        )

    # Pre-read body data if any handler param needs typed extraction
    plan = getattr(match.route, "invoke_plan", None)
    if plan is not None:
        body_data = await _read_body_if_needed_from_plan(plan, request)
    else:
        body_data = await _read_body_if_needed_inspect(handler, request)

    # Build kwargs from compiled plan or fallback to inspection
    kwargs = _build_handler_kwargs(
        handler,
        request,
        match.path_params,
        providers,
        body_data=body_data,
        invoke_plan=plan,
    )

    # Call the handler (sync or async — invoke() handles both).
    # When a compiled plan exists, pass cached flags to skip per-request inspect.
    # force_inline_sync overrides to_thread dispatch (set by Pounce sync workers
    # where the event loop is single-purpose and blocking is safe).
    invoke_kw: dict[str, Any] = {}
    if plan is not None:
        invoke_kw["is_async"] = plan.is_async
        invoke_kw["inline_sync"] = plan.inline_sync or force_inline_sync
    elif force_inline_sync:
        invoke_kw["inline_sync"] = True
    result = await invoke(handler, **invoke_kw, **kwargs)

    return negotiate(
        result,
        kida_env=kida_env,
        request=request,
        validate_blocks=validate_blocks,
        oob_registry=oob_registry,
        fragment_target_registry=fragment_target_registry,
    )


def _build_handler_kwargs(
    handler: Callable[..., Any],
    request: Request,
    path_params: dict[str, str],
    providers: dict[type, Callable[..., Any]] | None = None,
    *,
    body_data: dict[str, Any] | None = None,
    invoke_plan: InvokePlan | None = None,
) -> dict[str, Any]:
    """Build kwargs from request + path params using compiled plan or inspection.

    When invoke_plan is present, uses the precomputed plan (no inspect per request).
    Falls back to _build_handler_kwargs_inspect for routes without a plan.
    """
    if invoke_plan is not None:
        return _build_handler_kwargs_from_plan(
            request, path_params, providers, body_data, invoke_plan
        )
    return _build_handler_kwargs_inspect(handler, request, path_params, providers, body_data)


def _build_handler_kwargs_from_plan(
    request: Request,
    path_params: dict[str, str],
    providers: dict[type, Callable[..., Any]] | None,
    body_data: dict[str, Any] | None,
    plan: InvokePlan,
) -> dict[str, Any]:
    """Build kwargs using compiled InvokePlan — allocation-light fast path."""
    from chirp.extraction import extract_dataclass

    kwargs: dict[str, Any] = {}
    for spec in plan.params:
        if spec.source == "request":
            kwargs[spec.name] = request
        elif spec.source == "path" and spec.name in path_params:
            value = path_params[spec.name]
            if spec.annotation is not None:
                try:
                    kwargs[spec.name] = spec.annotation(value)
                except ValueError, TypeError:
                    kwargs[spec.name] = value
            else:
                kwargs[spec.name] = value
        elif spec.source == "provider" and spec.annotation and providers:
            provider = providers.get(spec.annotation)
            if provider is not None:
                kwargs[spec.name] = provider()
        elif spec.source == "extract" and spec.annotation is not None:
            if request.method in ("GET", "HEAD"):
                kwargs[spec.name] = extract_dataclass(spec.annotation, request.query)
            elif body_data is not None:
                kwargs[spec.name] = extract_dataclass(spec.annotation, body_data)
    return kwargs


def _build_handler_kwargs_inspect(
    handler: Callable[..., Any],
    request: Request,
    path_params: dict[str, str],
    providers: dict[type, Callable[..., Any]] | None,
    body_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fallback: inspect handler signature and build kwargs (used when no plan)."""
    import inspect

    from chirp.extraction import extract_dataclass, is_extractable_dataclass

    sig = inspect.signature(handler, eval_str=True)
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name == "request" or param.annotation is Request:
            kwargs[name] = request
        elif name in path_params:
            value = path_params[name]
            if param.annotation is not inspect.Parameter.empty:
                try:
                    kwargs[name] = param.annotation(value)
                except ValueError, TypeError:
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
            if request.method in ("GET", "HEAD"):
                kwargs[name] = extract_dataclass(param.annotation, request.query)
            elif body_data is not None:
                kwargs[name] = extract_dataclass(param.annotation, body_data)

    return kwargs


async def _read_body_if_needed_from_plan(
    plan: InvokePlan | None,
    request: Request,
) -> dict[str, Any] | None:
    """Pre-read form/JSON body if the handler has extractable dataclass params.

    Uses compiled plan when available.
    """
    if request.method in ("GET", "HEAD"):
        return None
    if plan is None or not plan.has_extract_param:
        return None

    ct = request.content_type or ""
    if "json" in ct:
        return await request.json()
    return dict(await request.form())


async def _read_body_if_needed_inspect(
    handler: Callable[..., Any],
    request: Request,
) -> dict[str, Any] | None:
    """Fallback: inspect handler for extractable params, read body if needed."""
    import inspect

    from chirp.extraction import is_extractable_dataclass

    if request.method in ("GET", "HEAD"):
        return None

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
