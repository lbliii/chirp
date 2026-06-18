"""ASGI handler — translates ASGI scope/messages to chirp types.

The only component that touches raw ASGI directly. Converts scope dicts
to typed Request objects, dispatches through middleware and routing,
and sends Response back through ASGI send().
"""

from collections.abc import Callable, Mapping
from contextvars import Token
from dataclasses import replace
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp._internal.invoke import invoke
from chirp._internal.invoke_plan import InvokePlan
from chirp.app.state import RuntimeDebugWiring
from chirp.context import force_inline_sync_var, g, request_var
from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import FileResponse, Response, SSEResponse, StreamingResponse
from chirp.logging import request_id_var
from chirp.middleware.protocol import AnyResponse, Next
from chirp.routing.route import RouteMatch
from chirp.routing.router import Router
from chirp.server.debug_runtime import (
    DEBUG_MANIFEST_PATH,
    DEBUG_TRACES_PATH,
    render_debug_manifest_json,
    render_debug_traces_json,
)
from chirp.server.devtools import (
    DEVTOOLS_BOOT_JS,
    DEVTOOLS_BOOT_PATH,
    HIGHLIGHT_PATH,
    handle_highlight_request,
)
from chirp.server.errors import handle_http_error, handle_internal_error
from chirp.server.fragment_dispatch import (
    FRAGMENT_DISPATCH_CACHE_KEY,
    FragmentDispatchTarget,
    _coerce_to_fragment,
    is_fragment_dispatch_request,
    resolve_fragment_dispatch_target,
)
from chirp.server.fragment_targets_debug import (
    FRAGMENT_TARGETS_DEBUG_PATH,
    render_fragment_targets_debug,
)
from chirp.server.handler_kwargs import build_handler_kwargs
from chirp.server.negotiation import negotiate
from chirp.server.route_explorer import ROUTE_EXPLORER_PATH, render_route_explorer
from chirp.server.sender import send_file_response, send_response, send_streaming_response
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.oob_registry import OOBRegistry
from chirp.templating.trace import encode_return_trace, get_return_trace
from chirp.tools.registry import ToolRegistry


def compile_middleware_chain(
    middleware: tuple[Callable[..., Any], ...],
    dispatch: Callable[[Request], Any],
) -> Callable[[Request], Any]:
    """Build middleware chain once. Returns async handler(req) -> Response."""

    async def dispatch_with_context(req: Request) -> AnyResponse:
        token: Token[Request] = request_var.set(req)
        try:
            return await dispatch(req)
        finally:
            request_var.reset(token)

    chain = dispatch_with_context
    for mw in reversed(middleware):
        inner = chain
        mw_ref = mw

        async def layer(req: Request, _mw: Any = mw_ref, _next: Next = inner) -> AnyResponse:
            token: Token[Request] = request_var.set(req)
            try:
                return await _mw(req, _next)
            finally:
                request_var.reset(token)

        chain = layer
    return chain


def _request_path_with_query(request: Request) -> str:
    """Return the request path including the raw query string when present."""
    raw = getattr(request.query, "_raw", b"")
    if isinstance(raw, bytes) and raw:
        return f"{request.path}?{raw.decode('latin-1')}"
    return request.path


def _cross_shell_boost_redirect(
    request: Request,
    match: RouteMatch,
    *,
    router: Router,
    route_layout_chains: Mapping[str, Any] | None,
    fragment_target_registry: FragmentTargetRegistry | None,
    swap_scope_map: Mapping[str, str] | None,
) -> Response | None:
    """Redirect boosted GETs that would render into the wrong shell.

    Emits ``HX-Redirect`` to the destination URL (forcing a full-page load
    on the client) when the framework cannot guarantee a correct fragment
    swap. The policy is conservative: only boosted GETs are affected, and
    we always prefer redirect over rendering a fragment into a target the
    destination shell cannot satisfy.

    Cases handled:
        1. App has shell configured but registries are inconsistent
           (framework setup bug) — redirect rather than render broken.
        2. Current and destination have separate layout chains with no
           shared navigation ancestor (true cross-shell) — redirect.
        3. Computed swap target does not match the client's ``HX-Target``
           (existing behavior).

    Apps without app-shell (empty ``swap_scope_map``) are unaffected:
        their boosted responses pass through to normal fragment rendering.
    """
    from chirp.pages.types import LayoutChain
    from chirp.templating.navigation_swap import (
        common_navigation_prefix_len,
        lookup_layout_chain_for_path,
        resolve_navigation_swap,
    )

    if request.method != "GET" or not request.is_boosted:
        return None
    # No app-shell configured → this function is a no-op. Boosted fragments
    # from non-shell apps render via the normal dispatch path.
    if not swap_scope_map:
        return None
    # Case 1: shell configured but registries missing → inconsistent state.
    # Redirect rather than render against partial metadata.
    if route_layout_chains is None or fragment_target_registry is None:
        return Response(body="").with_hx_redirect(_request_path_with_query(request))
    current_path = request.htmx_current_url_abs_path
    if current_path is None or not current_path.startswith("/"):
        # Cannot compute swap diff without a valid current URL — pass through
        return None
    dest_chain = route_layout_chains.get(match.route.path)
    if not isinstance(dest_chain, LayoutChain):
        return None
    current_chain = lookup_layout_chain_for_path(
        current_path,
        router=router,
        route_layout_chains=route_layout_chains,
    )
    # Case 2: both chains exist with layouts but share no navigation
    # ancestor → true cross-shell. Render would target a DOM that does
    # not exist in the current shell; redirect instead.
    if (
        isinstance(current_chain, LayoutChain)
        and current_chain.layouts
        and dest_chain.layouts
        and common_navigation_prefix_len(current_chain, dest_chain) == 0
    ):
        return Response(body="").with_hx_redirect(_request_path_with_query(request))
    resolution = resolve_navigation_swap(
        current_path=current_path,
        destination_path=request.path,
        layout_chain_current=current_chain,
        layout_chain_dest=dest_chain,
        registry=fragment_target_registry,
        swap_scope_map=swap_scope_map,
    )
    if resolution is None:
        # Same shell, or no shared ancestor detected above — pass through
        return None
    # Case 3: computed target doesn't match client's HX-Target — redirect.
    if request.htmx_target_id == resolution.target_id:
        return None
    return Response(body="").with_hx_redirect(_request_path_with_query(request))


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
    route_layout_chains: Mapping[str, Any] | None = None,
    swap_scope_map: Mapping[str, str] | None = None,
    discovered_routes: list[Any] | None = None,
    debug_wiring: RuntimeDebugWiring | None = None,
    suspense_error_template: str | None = None,
    suspense_error_block: str = "fallback",
) -> Callable[[Request], Any]:
    """Build the full middleware + dispatch chain once. Reuse per request."""
    routes = discovered_routes or []

    def _internal_response(req: Request, response: Response) -> Response:
        if debug_wiring is None:
            return response
        spec = debug_wiring.internal_route_for_path(req.path)
        if spec is None:
            return response
        return response.with_header("X-Chirp-Internal", "true").with_header(
            "X-Chirp-Internal-Owner",
            spec.owner,
        )

    async def dispatch(req: Request) -> AnyResponse:
        if debug and req.path == DEVTOOLS_BOOT_PATH:
            return _internal_response(
                req,
                Response(
                    body=DEVTOOLS_BOOT_JS,
                    content_type="application/javascript; charset=utf-8",
                    render_intent="full_page",
                ),
            )
        if debug and req.path == HIGHLIGHT_PATH:
            body = handle_highlight_request(req.query)
            return _internal_response(
                req,
                Response(
                    body=body,
                    content_type="application/json; charset=utf-8",
                    render_intent="full_page",
                ),
            )
        if debug and req.path == FRAGMENT_TARGETS_DEBUG_PATH:
            return _internal_response(
                req,
                Response(
                    body=render_fragment_targets_debug(fragment_target_registry),
                    content_type="application/json; charset=utf-8",
                    render_intent="full_page",
                ),
            )
        if debug and req.path == DEBUG_MANIFEST_PATH and debug_wiring is not None:
            return _internal_response(
                req,
                Response(
                    body=render_debug_manifest_json(debug_wiring),
                    content_type="application/json; charset=utf-8",
                    render_intent="full_page",
                ),
            )
        if debug and req.path == DEBUG_TRACES_PATH and debug_wiring is not None:
            include_internal = req.query.get("internal") in {"1", "true", "yes"}
            return _internal_response(
                req,
                Response(
                    body=render_debug_traces_json(
                        debug_wiring,
                        include_internal=include_internal,
                    ),
                    content_type="application/json; charset=utf-8",
                    render_intent="full_page",
                ),
            )
        if req.path == ROUTE_EXPLORER_PATH:
            if debug:
                path_filter = req.query.get("path", "")
                html_body = render_route_explorer(routes, path_filter=path_filter or None)
                return _internal_response(
                    req,
                    Response(
                        body=html_body,
                        content_type="text/html; charset=utf-8",
                        render_intent="full_page",
                    ),
                )
            from chirp.errors import NotFound

            raise NotFound()
        if tool_registry is not None and len(tool_registry) > 0 and req.path == mcp_path:
            from chirp.tools.handler import handle_mcp_request

            return await handle_mcp_request(req, tool_registry)
        fragment_target = req._cache.get(FRAGMENT_DISPATCH_CACHE_KEY)
        if isinstance(fragment_target, FragmentDispatchTarget):
            match = fragment_target.match
            fragment_block = fragment_target.block_name
        else:
            match = router.match(req.method, req.path)
            fragment_block = None
        return await _invoke_handler(
            match,
            req,
            router=router,
            kida_env=kida_env,
            providers=providers,
            validate_blocks=debug,
            force_inline_sync=force_inline_sync_var.get(),
            oob_registry=oob_registry,
            fragment_target_registry=fragment_target_registry,
            route_layout_chains=route_layout_chains,
            swap_scope_map=swap_scope_map,
            suspense_error_template=suspense_error_template,
            suspense_error_block=suspense_error_block,
            fragment_block=fragment_block,
        )

    chain = compile_middleware_chain(middleware, dispatch)

    async def dispatch_with_fragment_resolution(req: Request) -> AnyResponse:
        if not is_fragment_dispatch_request(req):
            return await chain(req)
        target = resolve_fragment_dispatch_target(router, req)
        target.request._cache[FRAGMENT_DISPATCH_CACHE_KEY] = target
        g.chirp_fragment_block = target.block_name
        return await chain(target.request)

    return dispatch_with_fragment_resolution


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
    max_request_body_size: int | None = None,
    max_upload_size: int | None = None,
    upload_spool_threshold: int | None = None,
    max_upload_parts: int | None = None,
    compiled_handler: Callable[[Request], Any] | None = None,
    oob_registry: OOBRegistry | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    url_for: Callable[..., str] | None = None,
    debug_wiring: RuntimeDebugWiring | None = None,
) -> None:
    """Process a single HTTP request through the full pipeline."""
    if scope["type"] != "http":
        return

    # Build Request from ASGI scope, threading the upload/body limits so
    # body()/stream()/form() can enforce them at the byte boundary.
    request = Request.from_asgi(
        scope,
        receive,
        url_for=url_for,
        max_request_body_size=max_request_body_size,
        max_upload_size=max_upload_size,
        upload_spool_threshold=upload_spool_threshold,
        max_upload_parts=max_upload_parts,
    )

    # Pounce sync workers set this so sync handlers run directly on the
    # worker thread instead of being dispatched through asyncio.to_thread().
    extensions = scope.get("extensions") or {}
    force_inline_sync = bool(extensions.get("pounce.inline_sync"))

    # Set request and request_id context vars (reset after dispatch)
    token: Token[Request] = request_var.set(request)
    rid_token = request_id_var.set(request.request_id)
    sync_token = force_inline_sync_var.set(force_inline_sync)

    if compiled_handler is None:
        msg = "compiled_handler is required; ASGIRuntime always provides it"
        raise RuntimeError(msg)

    try:
        response = await compiled_handler(request)
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
        # Release any spooled upload temp files parsed during this request so
        # spilled-to-disk uploads do not leak fds / temp files after response.
        cached_form = request._cache.get("_form")
        if cached_form is not None:
            close = getattr(cached_form, "close", None)
            if callable(close):
                close()
        g._reset()
        request_var.reset(token)
        request_id_var.reset(rid_token)
        force_inline_sync_var.reset(sync_token)

    # Dispatch based on response type — X-Request-ID injected at send time
    # to avoid an extra Response clone + tuple allocation per request.
    rid = request.request_id
    match response:
        case SSEResponse():
            from chirp.realtime.sse import handle_sse
            from chirp.server.streaming_context import _CapturedRequestContext

            stream = response.event_stream
            if stream.heartbeat_interval == 15.0:
                stream = replace(stream, heartbeat_interval=sse_heartbeat_interval)
            trace_sink = None
            extra_headers: tuple[tuple[bytes, bytes], ...] = ()
            return_trace = get_return_trace(request)
            if debug and return_trace is not None:
                extra_headers = (
                    (b"x-chirp-return-trace", encode_return_trace(return_trace).encode("ascii")),
                )
            if debug and debug_wiring is not None and debug_wiring.trace_store is not None:
                spec = debug_wiring.internal_route_for_path(request.path)
                internal = spec is not None and spec.visibility != "user"
                owner = spec.owner if spec is not None else "app"

                def _trace_sink(phase: str, data: dict[str, Any]) -> None:
                    debug_wiring.trace_store.record_sse(
                        phase=phase,
                        path=request.path,
                        request_id=request.request_id,
                        internal=internal,
                        owner=owner,
                        data=data,
                    )

                trace_sink = _trace_sink

            captured_context = _CapturedRequestContext(
                auth_user=response.auth_user,
                csrf_token=response.csrf_token,
                csrf_field_name=response.csrf_field_name,
                g_snapshot=response.g_snapshot,
                request_context=response.request_context,
                csp_nonce=response.csp_nonce,
            )
            await handle_sse(
                stream,
                send,
                receive,
                kida_env=response.kida_env,
                debug=debug,
                retry_ms=sse_retry_ms,
                close_event=sse_close_event,
                allow_origin=stream.allow_origin,
                trace_sink=trace_sink,
                extra_headers=extra_headers,
                captured_context=captured_context,
            )
        case StreamingResponse():
            await send_streaming_response(response, send, debug=debug, request_id=rid)
        case FileResponse():
            await send_file_response(
                response,
                send,
                request=request,
                is_head=request.method == "HEAD",
                request_id=rid,
            )
        case _:
            await send_response(response, send, request_id=rid)


async def _invoke_handler(
    match: RouteMatch,
    request: Request,
    *,
    router: Router,
    kida_env: Environment | None = None,
    providers: dict[type, Callable[..., Any]] | None = None,
    validate_blocks: bool = False,
    force_inline_sync: bool = False,
    oob_registry: OOBRegistry | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    route_layout_chains: Mapping[str, Any] | None = None,
    swap_scope_map: Mapping[str, str] | None = None,
    suspense_error_template: str | None = None,
    suspense_error_block: str = "fallback",
    fragment_block: str | None = None,
) -> AnyResponse:
    """Call the matched route handler, converting path params and return value."""
    handler = match.route.handler

    # Inject path_params into Request; skip clone when already identical
    if request.path_params != match.path_params:
        request = replace(request, path_params=match.path_params)

    cross_shell_redirect = _cross_shell_boost_redirect(
        request,
        match,
        router=router,
        route_layout_chains=route_layout_chains,
        fragment_target_registry=fragment_target_registry,
        swap_scope_map=swap_scope_map,
    )
    if cross_shell_redirect is not None:
        return cross_shell_redirect

    # Pre-read body data if any handler param needs typed extraction
    plan = getattr(match.route, "invoke_plan", None)
    if plan is not None:
        body_data = await _read_body_if_needed_from_plan(plan, request)
    else:
        body_data = await _read_body_if_needed_inspect(handler, request)

    # Build kwargs from compiled plan or fallback to inspection
    kwargs = build_handler_kwargs(
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
    if fragment_block is not None:
        result = _coerce_to_fragment(result, fragment_block)

    return negotiate(
        result,
        kida_env=kida_env,
        request=request,
        validate_blocks=validate_blocks,
        oob_registry=oob_registry,
        fragment_target_registry=fragment_target_registry,
        suspense_error_template=suspense_error_template,
        suspense_error_block=suspense_error_block,
    )


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
