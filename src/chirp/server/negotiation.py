"""Content negotiation — maps return values to Response objects.

The ContentNegotiator inspects the return value from a route handler
and produces the appropriate Response. isinstance-based dispatch,
no magic, fully predictable.
"""

import logging
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
from chirp.realtime.events import EventStream
from chirp.server.debug.render_plan_snapshot import stash_render_debug_for_request
from chirp.server.negotiation_oob import (
    append_shell_actions_oob_stream,
    compute_shell_region_updates,
    should_append_streamed_shell_actions_oob,
)
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
    FormAction,
    Fragment,
    InlineTemplate,
    LayoutPage,
    LayoutSuspense,
    Page,
    Stream,
    Suspense,
    Template,
    TemplateStream,
    ValidationError,
)
from chirp.templating.streaming import has_async_context, render_stream_async
from chirp.templating.suspense import render_suspense

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
    instances instead of ``dataclasses.replace`` (which does not pass ``name``).
    """
    if request is None or "current_path" in value.context:
        return value
    new_ctx = {**value.context, "current_path": request.path}
    if isinstance(value, Template):
        return Template(value.name, **new_ctx)
    if isinstance(value, Page):
        return Page(
            value.name,
            value.block_name,
            page_block_name=value.page_block_name,
            **new_ctx,
        )
    return LayoutPage(
        value.name,
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
) -> Response:
    """Shared 5-step pipeline: shell updates → plan → execute → serialize → response."""
    shell_updates = compute_shell_region_updates(composition, request, fragment_target_registry)
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
    return _html_response(html, intent=intent)


def _set_layout_debug_from_plan(plan: Any, request: Request | None) -> None:
    """Set layout debug metadata for LayoutDebugMiddleware when config.debug."""
    if request is None or plan.layout_chain is None or not plan.layout_chain.layouts:
        return
    try:
        from chirp.middleware.layout_debug import set_layout_debug_metadata

        layouts = plan.layout_chain.layouts
        chain_str = " > ".join(f"{lay.target}({i})" for i, lay in enumerate(layouts))
        target_id = (request.htmx_target or "").lstrip("#")
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
) -> Response | StreamingResponse | SSEResponse:
    """Convert a route handler's return value to a Response.

    Dispatch order:

    1. ``Response``         -> pass through
    2. ``Redirect``         -> 302 with Location header
    3. ``FormAction``       -> htmx: fragments or HX-Redirect; non-htmx: 303
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
            return value
        case Redirect():
            return (
                Response(body="")
                .with_status(value.status)
                .with_header("Location", value.url)
                .with_headers(dict(value.headers))
            )
        case FormAction():
            if request is not None and request.is_fragment:
                if value.fragments and kida_env is not None:
                    parts = [render_fragment(kida_env, frag) for frag in value.fragments]
                    html = "\n".join(parts)
                    response = _fragment_response(html)
                    if value.trigger:
                        response = response.with_hx_trigger(value.trigger)
                    return response
                else:
                    return Response(body="").with_hx_redirect(value.redirect)
            else:
                return (
                    Response(body="")
                    .with_status(value.status)
                    .with_header("Location", value.redirect)
                )
        case Template():
            kida_env = _require_kida_env(kida_env, "Template")
            html = render_template(kida_env, _with_current_path_in_context(value, request))
            return _html_response(html, intent="full_page")
        case InlineTemplate():
            env = kida_env or _minimal_kida_env()
            tmpl = env.from_string(value.source)
            html = tmpl.render(value.context)
            return _html_response(html, intent="full_page")
        case Fragment():
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
            )
        case Action():
            response = Response(body="").with_status(value.status)
            if value.trigger is not None:
                response = response.with_hx_trigger(value.trigger)
            if value.refresh:
                response = response.with_hx_refresh()
            return response
        case ValidationError():
            kida_env = _require_kida_env(kida_env, "ValidationError")
            frag = Fragment(value.template_name, value.block_name, **value.context)
            html = render_fragment(kida_env, frag)
            response = _fragment_response(html).with_status(422)
            if value.retarget is not None:
                response = response.with_hx_retarget(value.retarget)
            return response
        case OOB():
            kida_env = _require_kida_env(kida_env, "OOB")
            main_response = negotiate(
                value.main,
                kida_env=kida_env,
                request=request,
                oob_registry=oob_registry,
                fragment_target_registry=fragment_target_registry,
            )
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
            return _fragment_response(body)
        case Stream():
            kida_env = _require_kida_env(kida_env, "Stream")
            if has_async_context(value.context):
                # Async sources detected — resolve concurrently, then stream
                chunks = render_stream_async(kida_env, value)
                return StreamingResponse(
                    chunks=chunks,
                    content_type="text/html; charset=utf-8",
                )
            # All context values are resolved — use sync streaming
            tmpl = kida_env.get_template(value.template_name)
            chunks = tmpl.render_stream(value.context)
            return StreamingResponse(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
            )
        case TemplateStream():
            kida_env = _require_kida_env(kida_env, "TemplateStream")
            tmpl = kida_env.get_template(value.template_name)
            chunks = tmpl.render_stream_async(**value.context)
            return StreamingResponse(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
            )
        case LayoutSuspense():
            kida_env = _require_kida_env(kida_env, "LayoutSuspense")
            req = value.request if value.request is not None else request
            is_htmx = bool(req and req.is_fragment)
            chunks = render_suspense(
                kida_env,
                value.suspense,
                is_htmx=is_htmx,
                layout_chain=value.layout_chain,
                layout_context=value.context,
                request=req,
                oob_registry=oob_registry,
            )
            if should_append_streamed_shell_actions_oob(value.context, req):
                chunks = append_shell_actions_oob_stream(chunks, value.context, kida_env)
            return StreamingResponse(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
            )
        case Suspense():
            kida_env = _require_kida_env(kida_env, "Suspense")
            is_htmx = request is not None and request.is_fragment
            chunks = render_suspense(kida_env, value, is_htmx=is_htmx, oob_registry=oob_registry)
            return StreamingResponse(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
            )
        case EventStream():
            return SSEResponse(
                event_stream=value,
                kida_env=kida_env,
            )
        case str():
            return _html_response(value, intent="unknown")
        case bytes():
            return Response(body=value, content_type="application/octet-stream")
        case dict() | list():
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
                f"TemplateStream, Action, Stream, EventStream, Response, or Redirect."
            )
            raise TypeError(msg)
