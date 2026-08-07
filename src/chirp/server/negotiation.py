"""Content negotiation — maps return values to Response objects.

The ContentNegotiator inspects the return value from a route handler
and produces the appropriate Response. isinstance-based dispatch,
no magic, fully predictable.
"""

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any, overload

from kida import Environment

from chirp.errors import ConfigurationError
from chirp.http.response import (
    JSONResponse,
    Redirect,
    RenderIntent,
    Response,
    SSEResponse,
    StreamingResponse,
)
from chirp.middleware.csp_nonce import csp_nonce as _get_csp_nonce
from chirp.realtime.events import EventStream
from chirp.server.debug.render_plan_snapshot import stash_render_debug_for_request
from chirp.server.negotiation_oob import (
    append_layout_oob_stream,
    append_shell_actions_oob_stream,
    compute_shell_region_updates,
    should_append_layout_oob,
    should_append_streamed_shell_actions_oob,
)
from chirp.server.streaming_context import (
    attach_streaming_render_context,
    capture_streaming_render_context,
)
from chirp.shell_actions import ShellActionsRenderer
from chirp.skill.envelope import Envelope
from chirp.templating.composition import PageComposition
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.integration import render_fragment, render_template
from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.oob_registry import OOBRegistry
from chirp.templating.render_plan import (
    build_render_plan,
    execute_render_plan,
    normalize_to_composition,
    serialize_rendered_plan,
)
from chirp.templating.returns import (
    OOB,
    Action,
    Fragment,
    InlineTemplate,
    LayoutPage,
    LayoutSuspense,
    MutationResult,
    Page,
    SignalEmit,
    Stream,
    Suspense,
    Template,
    TemplateStream,
    ValidationError,
)
from chirp.templating.streaming import has_async_context, render_stream_async
from chirp.templating.suspense import render_suspense
from chirp.templating.trace import ReturnTrace, stash_return_trace_for_request

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from chirp.http.request import Request


def _minimal_kida_env() -> Environment:
    """Create a bare kida Environment for inline template rendering.

    Used when no template_dir is configured but an InlineTemplate
    needs to be rendered (prototyping without any file templates).
    """
    return Environment()


def _html_response(body: str, *, intent: RenderIntent) -> Response:
    """Build a text/html response with explicit render intent."""
    return Response(
        body=body,
        content_type="text/html; charset=utf-8",
        render_intent=intent,
    )


def _fragment_response(body: str) -> Response:
    """Build a text/html response for fragment-returning endpoints."""
    return _html_response(body, intent="fragment")


def _require_kida_env(kida_env: Environment | None, return_type: str) -> Environment:
    """Raise ConfigurationError if kida_env is None (template return types need it)."""
    if kida_env is None:
        msg = (
            f"{return_type} return type requires kida integration. "
            "Ensure a template_dir is configured in AppConfig."
        )
        raise ConfigurationError(msg)
    return kida_env


def _context_keys(ctx: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(key) for key in ctx)


def _is_htmx(request: Request | None) -> bool:
    return bool(request and request.is_htmx)


def _trace_request_content_type(request: Request | None) -> str | None:
    """Return bounded request media metadata for a debug response header."""
    if request is None or request.content_type is None:
        return None
    value = request.content_type
    return value if len(value) <= 256 else value[:253] + "..."


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _normalize_hx_redirect_response(response: Response, request: Request | None) -> Response:
    """Strip conflicting redirect headers for htmx vs non-htmx clients (#272)."""
    hx_url = response.header("HX-Redirect")
    if hx_url is None:
        return response

    if _is_htmx(request):
        headers = tuple(
            (name, value) for name, value in response.headers if name.lower() != "location"
        )
        status = 200 if response.status in _REDIRECT_STATUSES else response.status
        return replace(response, status=status, headers=headers)

    headers = tuple(
        (name, value) for name, value in response.headers if name.lower() != "hx-redirect"
    )
    return replace(response, headers=headers)


def _streaming_response(**kwargs: Any) -> StreamingResponse:
    return attach_streaming_render_context(StreamingResponse(**kwargs))


def _trace_return(
    request: Request | None,
    *,
    return_type: str,
    category: str,
    render_intent: str = "unknown",
    status: int | None = None,
    template: str | None = None,
    block: str | None = None,
    target: str | None = None,
    swap: str | None = None,
    context_keys: tuple[str, ...] = (),
    streaming: bool = False,
    sse: bool = False,
    notes: tuple[str, ...] = (),
) -> None:
    stash_return_trace_for_request(
        ReturnTrace(
            return_type=return_type,
            category=category,
            is_htmx=_is_htmx(request),
            method=request.method if request is not None else None,
            request_content_type=_trace_request_content_type(request),
            render_intent=render_intent,
            status=status,
            template=template,
            block=block,
            target=target,
            swap=swap,
            context_keys=context_keys,
            streaming=streaming,
            sse=sse,
            notes=notes,
        ),
        request,
    )


@overload
def _with_current_path_in_context(value: Template, request: Request | None) -> Template: ...


@overload
def _with_current_path_in_context(
    value: Page | LayoutPage,
    request: Request | None,
) -> Page | LayoutPage: ...


def _with_current_path_in_context(
    value: Template | Page | LayoutPage,
    request: Request | None,
) -> Template | Page | LayoutPage:
    """Return *value* with ``current_path`` merged into context (copy-on-write).

    Avoids mutating a shared ``context`` dict when handlers reuse a frozen
    ``Template``/``Page``/``LayoutPage`` across requests.

    ``Template``/``Page``/``LayoutPage`` use custom ``__init__`` — construct fresh
    instances instead of ``dataclasses.replace`` (which does not pass ``template_name``).
    """
    if request is None or "current_path" in value.context:
        return value
    new_ctx = {**value.context, "current_path": request.path}
    if isinstance(value, Template):
        return Template(value.template_name, **new_ctx)
    if isinstance(value, Page):
        return Page(
            value.template_name,
            value.block_name,
            page_block_name=value.page_block_name,
            **new_ctx,
        )
    return LayoutPage(
        value.template_name,
        value.block_name,
        page_block_name=value.page_block_name,
        layout_chain=value.layout_chain,
        context_providers=value.context_providers,
        **new_ctx,
    )


def _render_composition(
    composition: PageComposition,
    request: Request | None,
    fragment_target_registry: FragmentTargetRegistry | None,
    kida_env: Environment,
    validate_blocks: bool,
    oob_registry: OOBRegistry | None,
    shell_actions_renderer: ShellActionsRenderer | None = None,
) -> Response:
    """Shared 5-step pipeline: shell updates → plan → execute → serialize → response.

    Sets ``Vary: HX-Request, HX-Request-Type`` because the response varies by
    htmx transport and by htmx 4 full/partial intent. Without this, HTTP caches
    may replay the wrong fragment width or serve a fragment to a full-page
    request.
    """
    shell_updates = compute_shell_region_updates(
        composition, request, fragment_target_registry, shell_actions_renderer
    )
    plan = build_render_plan(
        composition,
        request=request,
        fragment_target_registry=fragment_target_registry,
        shell_region_updates=shell_updates,
    )
    stash_render_debug_for_request(plan, request, debug=validate_blocks)
    _set_layout_debug_from_plan(plan, request)
    adapter = KidaAdapter(kida_env)
    rendered = execute_render_plan(
        plan,
        adapter=adapter,
        validate_blocks=validate_blocks,
        oob_registry=oob_registry,
    )
    html = serialize_rendered_plan(rendered, oob_registry=oob_registry)
    intent = "fragment" if plan.intent != "full_page" else "full_page"
    _trace_return(
        request,
        return_type="PageComposition",
        category="page",
        render_intent=intent,
        status=200,
        template=plan.main_view.template,
        block=plan.main_view.block,
        context_keys=_context_keys(plan.main_view.context),
        notes=(f"plan_intent={plan.intent}",),
    )
    response = _html_response(html, intent=intent).with_vary("HX-Request", "HX-Request-Type")
    for name, value in plan.response_headers.items():
        response = response.with_header(name, value)
    return response


def _set_layout_debug_from_plan(plan: Any, request: Request | None) -> None:
    """Set layout debug metadata for LayoutDebugMiddleware when config.debug."""
    if request is None or plan.layout_chain is None or not plan.layout_chain.layouts:
        return
    try:
        from chirp.middleware.layout_debug import set_layout_debug_metadata

        layouts = plan.layout_chain.layouts
        chain_str = " > ".join(f"{lay.target}({i})" for i, lay in enumerate(layouts))
        target_id = request.htmx_target_id or ""
        rendered = len(layouts[plan.layout_start_index :])
        mode = "full" if plan.intent == "full_page" else "fragment"
        if plan.layout_start_index > 0 and plan.layout_start_index < len(layouts):
            mode = "partial"
        match_str = f"target={target_id}, start={plan.layout_start_index}, rendered={rendered}"
        set_layout_debug_metadata(request, chain_str, match_str, mode)
    except ImportError:
        pass


def negotiate(
    value: Any,
    *,
    kida_env: Environment | None = None,
    request: Request | None = None,
    validate_blocks: bool = False,
    oob_registry: OOBRegistry | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    suspense_error_template: str | None = None,
    suspense_error_block: str = "fallback",
    shell_actions_renderer: ShellActionsRenderer | None = None,
) -> Response | StreamingResponse | SSEResponse:
    """Convert a route handler's return value to a Response.

    Dispatch order:

    1. ``Response``         -> pass through
    2. ``Redirect``         -> 302 with Location header
    3. ``MutationResult``   -> htmx: fragments or HX-Redirect; non-htmx: 303
    4. ``Template``         -> render via kida -> Response
    5. ``Fragment``         -> render block via kida -> Response
    6. ``Page``             -> Template or Fragment based on request headers
    7. ``Action``           -> empty Response + optional HX headers
    8. ``ValidationError``  -> Fragment + 422 + optional HX-Retarget
    9. ``OOB``              -> primary + hx-swap-oob fragments
    10. ``Stream``           -> kida render_stream() -> StreamingResponse
                               (async sources resolved concurrently)
    11. ``TemplateStream``   -> kida render_stream_async() -> StreamingResponse
    12. ``Suspense``         -> shell + deferred OOB blocks -> StreamingResponse
                               (first paint instant, blocks fill in)
    13. ``EventStream``      -> SSEResponse (handler dispatches to SSE)
    14. ``str``              -> 200, text/html
    15. ``bytes``            -> 200, application/octet-stream
    16. ``dict`` / ``list``  -> 200, application/json
    17. ``(value, int)``     -> negotiate value, override status
    18. ``(value, int, dict)`` -> negotiate value, override status + headers
    """
    match value:
        case Response():
            _trace_return(
                request,
                return_type=type(value).__name__,
                category="response",
                render_intent=value.render_intent,
                status=value.status,
            )
            return _normalize_hx_redirect_response(value, request)
        case Redirect():
            _trace_return(
                request,
                return_type="Redirect",
                category="redirect",
                status=value.status,
                target=value.url,
            )
            return (
                Response(body="")
                .with_status(value.status)
                .with_header("Location", value.url)
                .with_headers(dict(value.headers))
            )
        case MutationResult():
            if request is not None and request.is_htmx:
                if value.fragments:
                    first = value.fragments[0]
                    _trace_return(
                        request,
                        return_type="MutationResult",
                        category="mutation",
                        render_intent="fragment",
                        status=200,
                        template=first.template_name,
                        block=first.block_name,
                        target=first.target,
                        context_keys=_context_keys(first.context),
                        notes=(f"fragments={len(value.fragments)}",),
                    )
                    kida_env = _require_kida_env(kida_env, "MutationResult")
                    parts: list[str] = []
                    for i, frag in enumerate(value.fragments):
                        html = render_fragment(kida_env, frag)
                        if i == 0:
                            # First fragment is the primary swap target
                            parts.append(html)
                        else:
                            # Secondary fragments use OOB swap
                            target_id = frag.target if frag.target is not None else frag.block_name
                            swap_attr = getattr(frag, "swap", None)
                            if swap_attr is None and oob_registry is not None:
                                swap_attr, wrap = oob_registry.resolve_serialization(target_id)
                            else:
                                wrap = True
                            if swap_attr is None:
                                swap_attr = "true"
                            if wrap:
                                parts.append(
                                    f'<div id="{target_id}" hx-swap-oob="{swap_attr}">{html}</div>'
                                )
                            else:
                                parts.append(html)
                    html = "\n".join(parts)
                    response = _fragment_response(html)
                    if value.trigger:
                        response = response.with_hx_trigger(value.trigger)
                    return response
                else:
                    _trace_return(
                        request,
                        return_type="MutationResult",
                        category="mutation_redirect",
                        status=200,
                        target=value.redirect,
                    )
                    return Response(body="").with_hx_redirect(value.redirect)
            else:
                _trace_return(
                    request,
                    return_type="MutationResult",
                    category="mutation_redirect",
                    status=value.status,
                    target=value.redirect,
                )
                return (
                    Response(body="")
                    .with_status(value.status)
                    .with_header("Location", value.redirect)
                )
        case Template():
            _trace_return(
                request,
                return_type="Template",
                category="template",
                render_intent="full_page",
                status=200,
                template=value.template_name,
                context_keys=_context_keys(value.context),
            )
            kida_env = _require_kida_env(kida_env, "Template")
            html = render_template(kida_env, _with_current_path_in_context(value, request))
            return _html_response(html, intent="full_page")
        case InlineTemplate():
            _trace_return(
                request,
                return_type="InlineTemplate",
                category="template",
                render_intent="full_page",
                status=200,
                context_keys=_context_keys(value.context),
            )
            env = kida_env or _minimal_kida_env()
            tmpl = env.from_string(value.source)
            html = tmpl.render(value.context)
            return _html_response(html, intent="full_page")
        case Fragment():
            _trace_return(
                request,
                return_type="Fragment",
                category="fragment",
                render_intent="fragment",
                status=200,
                template=value.template_name,
                block=value.block_name,
                target=value.target,
                swap=value.swap,
                context_keys=_context_keys(value.context),
            )
            kida_env = _require_kida_env(kida_env, "Fragment")
            html = render_fragment(kida_env, value)
            return _fragment_response(html)
        case Page() | LayoutPage():
            kida_env = _require_kida_env(kida_env, "Page/LayoutPage")
            value = _with_current_path_in_context(value, request)
            composition = normalize_to_composition(value)
            if composition is None:
                msg = f"Cannot normalize {type(value).__name__} to composition"
                raise TypeError(msg)
            return _render_composition(
                composition,
                request,
                fragment_target_registry,
                kida_env,
                validate_blocks,
                oob_registry,
                shell_actions_renderer,
            )
        case PageComposition():
            kida_env = _require_kida_env(kida_env, "PageComposition")
            return _render_composition(
                value,
                request,
                fragment_target_registry,
                kida_env,
                validate_blocks,
                oob_registry,
                shell_actions_renderer,
            )
        case Action():
            _trace_return(
                request,
                return_type="Action",
                category="action",
                status=value.status,
                notes=(f"refresh={value.refresh}",),
            )
            response = Response(body="").with_status(value.status)
            if value.trigger is not None:
                response = response.with_hx_trigger(value.trigger)
            if value.refresh:
                response = response.with_hx_refresh()
            return response
        case SignalEmit():
            from chirp.realtime.emit_bridge import emit_signal

            notes: list[str] = []
            for name, payload in value.items:
                emit_signal(name, payload)
                notes.append(f"emit {name}")
            _trace_return(
                request,
                return_type="SignalEmit",
                category="mutation",
                render_intent="none",
                status=value.status,
                notes=tuple(notes),
            )
            return Response(body="").with_status(value.status)
        case ValidationError():
            _trace_return(
                request,
                return_type="ValidationError",
                category="validation",
                render_intent="fragment",
                status=422,
                template=value.template_name,
                block=value.block_name,
                target=value.retarget,
                context_keys=_context_keys(value.context),
            )
            kida_env = _require_kida_env(kida_env, "ValidationError")
            frag = Fragment(value.template_name, value.block_name, **value.context)
            html = render_fragment(kida_env, frag)
            response = _fragment_response(html).with_status(422)
            if value.retarget is not None:
                response = response.with_hx_retarget(value.retarget)
            return response
        case OOB():
            _trace_return(
                request,
                return_type="OOB",
                category="oob",
                render_intent="fragment",
                status=200,
                notes=(f"oob_fragments={len(value.oob_fragments)}",),
            )
            kida_env = _require_kida_env(kida_env, "OOB")
            main_response = negotiate(
                value.main,
                kida_env=kida_env,
                request=request,
                oob_registry=oob_registry,
                fragment_target_registry=fragment_target_registry,
            )
            if isinstance(main_response, StreamingResponse):
                msg = (
                    "OOB main cannot be a StreamingResponse "
                    "(e.g. EventStream, Suspense, Stream). "
                    "OOB requires a buffered response to append fragments. "
                    "Buffered return types: Template, Fragment, Page, "
                    "MutationResult/FormAction, ValidationError. Streaming types "
                    "(Stream, Suspense, EventStream) cannot carry OOB siblings — "
                    "yield additional Fragment values from inside the stream instead."
                )
                raise TypeError(msg)
            parts: list[str] = [main_response.text if isinstance(main_response, Response) else ""]
            for frag in value.oob_fragments:
                html = render_fragment(kida_env, frag)
                target_id = frag.target if frag.target is not None else frag.block_name
                swap_attr = getattr(frag, "swap", None)
                if swap_attr is None and oob_registry is not None:
                    swap_attr, wrap = oob_registry.resolve_serialization(target_id)
                else:
                    wrap = True
                if swap_attr is None:
                    swap_attr = "true"
                if wrap:
                    parts.append(f'<div id="{target_id}" hx-swap-oob="{swap_attr}">{html}</div>')
                else:
                    parts.append(html)
            body = "\n".join(parts)
            _trace_return(
                request,
                return_type="OOB",
                category="oob",
                render_intent="fragment",
                status=200,
                notes=(f"oob_fragments={len(value.oob_fragments)}",),
            )
            return _fragment_response(body)
        case Stream():
            async_context = has_async_context(value.context)
            _trace_return(
                request,
                return_type="Stream",
                category="stream",
                status=200,
                template=value.template_name,
                context_keys=_context_keys(value.context),
                streaming=True,
                notes=("async_context" if async_context else "sync_context",),
            )
            kida_env = _require_kida_env(kida_env, "Stream")
            # Always render off the event loop via the worker-thread + bounded
            # queue bridge — for an all-sync context render_stream_async simply
            # resolves nothing and drives kida's CPU-bound sync generator on the
            # worker thread. Iterating render_stream() inline here (the old sync
            # branch) would block the loop for every concurrent request, which is
            # exactly what issue #179 targets. (async_context is kept only for
            # the trace note above.)
            chunks = render_stream_async(kida_env, value)
            return _streaming_response(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
                request_context=request,
                csp_nonce=_get_csp_nonce() or None,
            )
        case TemplateStream():
            _trace_return(
                request,
                return_type="TemplateStream",
                category="stream",
                status=200,
                template=value.template_name,
                context_keys=_context_keys(value.context),
                streaming=True,
            )
            kida_env = _require_kida_env(kida_env, "TemplateStream")
            tmpl = kida_env.get_template(value.template_name)
            chunks = tmpl.render_stream_async(**value.context)
            return _streaming_response(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
                request_context=request,
                csp_nonce=_get_csp_nonce() or None,
            )
        case LayoutSuspense():
            req = value.request if value.request is not None else request
            _trace_return(
                req,
                return_type="LayoutSuspense",
                category="suspense",
                status=200,
                template=value.suspense.template_name,
                context_keys=_context_keys(value.suspense.context),
                streaming=True,
                notes=(
                    f"defer_map={len(value.suspense.defer_map)}",
                    f"defer_blocks={len(value.suspense.defer_blocks or ())}",
                    "layout=true",
                ),
            )
            kida_env = _require_kida_env(kida_env, "LayoutSuspense")
            is_htmx = bool(req and req.is_htmx)
            chunks = render_suspense(
                kida_env,
                value.suspense,
                is_htmx=is_htmx,
                layout_chain=value.layout_chain,
                layout_context=value.context,
                request=req,
                oob_registry=oob_registry,
                fragment_target_registry=fragment_target_registry,
                error_template=suspense_error_template,
                error_block=suspense_error_block,
            )
            if should_append_streamed_shell_actions_oob(value.context, req):
                chunks = append_shell_actions_oob_stream(
                    chunks, value.context, kida_env, shell_actions_renderer
                )
            if should_append_layout_oob(req, value.layout_chain):
                chunks = append_layout_oob_stream(
                    chunks, kida_env, value.layout_chain, value.context, oob_registry
                )
            return _streaming_response(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
                request_context=req,
                csp_nonce=_get_csp_nonce() or None,
            )
        case Suspense():
            _trace_return(
                request,
                return_type="Suspense",
                category="suspense",
                status=200,
                template=value.template_name,
                context_keys=_context_keys(value.context),
                streaming=True,
                notes=(
                    f"defer_map={len(value.defer_map)}",
                    f"defer_blocks={len(value.defer_blocks or ())}",
                ),
            )
            kida_env = _require_kida_env(kida_env, "Suspense")
            is_htmx = request is not None and request.is_htmx
            chunks = render_suspense(
                kida_env,
                value,
                is_htmx=is_htmx,
                oob_registry=oob_registry,
                error_template=suspense_error_template,
                error_block=suspense_error_block,
            )
            return _streaming_response(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
                request_context=request,
                csp_nonce=_get_csp_nonce() or None,
            )
        case EventStream():
            _trace_return(
                request,
                return_type="EventStream",
                category="eventstream",
                status=200,
                streaming=True,
                sse=True,
            )
            # Capture the full request-scoped context (request, auth user, CSRF,
            # g, CSP nonce) while middleware ContextVars are still live. The
            # handler finally resets them before handle_sse drains, so the SSE
            # producer re-establishes this snapshot for the connection lifetime.
            captured = capture_streaming_render_context(
                request_context=request,
                csp_nonce=_get_csp_nonce() or None,
            )
            return SSEResponse(
                event_stream=value,
                kida_env=kida_env,
                csp_nonce=captured.csp_nonce,
                request_context=captured.request_context,
                auth_user=captured.auth_user,
                csrf_token=captured.csrf_token,
                csrf_field_name=captured.csrf_field_name,
                g_snapshot=captured.g_snapshot,
                runtime_context=captured.runtime_context,
            )
        case str():
            _trace_return(
                request,
                return_type="str",
                category="primitive",
                render_intent="unknown",
                status=200,
            )
            return _html_response(value, intent="unknown")
        case bytes():
            _trace_return(
                request,
                return_type="bytes",
                category="primitive",
                status=200,
            )
            return Response(body=value, content_type="application/octet-stream")
        case Envelope():
            # Signed skill result — wire dict as JSON (dict/list precedent).
            _trace_return(
                request,
                return_type="Envelope",
                category="primitive",
                status=200,
            )
            return JSONResponse.from_value(value.to_wire())
        case dict() | list():
            _trace_return(
                request,
                return_type=type(value).__name__,
                category="primitive",
                status=200,
            )
            return JSONResponse.from_value(value)
        case (inner, int() as status):
            response = negotiate(
                inner,
                kida_env=kida_env,
                request=request,
                oob_registry=oob_registry,
                fragment_target_registry=fragment_target_registry,
            )
            if isinstance(response, Response):
                return response.with_status(status)
            return response
        case (inner, int() as status, dict() as headers):
            response = negotiate(
                inner,
                kida_env=kida_env,
                request=request,
                oob_registry=oob_registry,
                fragment_target_registry=fragment_target_registry,
            )
            if isinstance(response, Response):
                return response.with_status(status).with_headers(headers)
            return response
        case _:
            msg = (
                f"Cannot convert {type(value).__name__} to a response. "
                f"Return str, dict, bytes, Template, InlineTemplate, Fragment, "
                f"TemplateStream, Action, Stream, EventStream, Envelope, "
                f"Response, or Redirect."
            )
            raise TypeError(msg)
