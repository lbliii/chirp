"""Content negotiation — maps return values to Response objects.

The ContentNegotiator inspects the return value from a route handler
and produces the appropriate Response. isinstance-based dispatch,
no magic, fully predictable.
"""

import json as json_module
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp.errors import ConfigurationError
from chirp.http.response import Redirect, RenderIntent, Response, SSEResponse, StreamingResponse
from chirp.pages.shell_actions import (
    SHELL_ACTIONS_CONTEXT_KEY,
    SHELL_ACTIONS_TARGET,
    normalize_shell_actions,
    shell_actions_fragment,
)
from chirp.realtime.events import EventStream
from chirp.templating.composition import PageComposition
from chirp.templating.integration import render_fragment, render_template
from chirp.templating.kida_adapter import KidaAdapter
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
    resp = Response(
        body=body,
        content_type="text/html; charset=utf-8",
        render_intent=intent,
    )
    if intent == "fragment":
        resp = resp.with_header("HX-Reselect", "*")
    return resp


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
                    response = _html_response(html, intent="fragment")
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
            if kida_env is None:
                msg = (
                    "Template return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            html = render_template(kida_env, value)
            return _html_response(html, intent="full_page")
        case InlineTemplate():
            env = kida_env or _minimal_kida_env()
            tmpl = env.from_string(value.source)
            html = tmpl.render(value.context)
            return _html_response(html, intent="full_page")
        case Fragment():
            if kida_env is None:
                msg = (
                    "Fragment return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            html = render_fragment(kida_env, value)
            return _html_response(html, intent="fragment")
        case Page() | LayoutPage():
            if kida_env is None:
                msg = (
                    "Page/LayoutPage return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            composition = normalize_to_composition(value)
            if composition is None:
                msg = f"Cannot normalize {type(value).__name__} to composition"
                raise TypeError(msg)
            plan = build_render_plan(composition, request=request)
            _set_layout_debug_from_plan(plan, request)
            adapter = KidaAdapter(kida_env)
            rendered = execute_render_plan(
                plan, adapter=adapter, validate_blocks=validate_blocks
            )
            html = serialize_rendered_plan(rendered)
            intent = "fragment" if plan.intent != "full_page" else "full_page"
            return _html_response(html, intent=intent)
        case PageComposition():
            if kida_env is None:
                msg = (
                    "PageComposition return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            plan = build_render_plan(value, request=request)
            _set_layout_debug_from_plan(plan, request)
            adapter = KidaAdapter(kida_env)
            rendered = execute_render_plan(
                plan, adapter=adapter, validate_blocks=validate_blocks
            )
            html = serialize_rendered_plan(rendered)
            intent = "fragment" if plan.intent != "full_page" else "full_page"
            return _html_response(html, intent=intent)
        case Action():
            response = Response(body="").with_status(value.status)
            if value.trigger is not None:
                response = response.with_hx_trigger(value.trigger)
            if value.refresh:
                response = response.with_hx_refresh()
            return response
        case ValidationError():
            if kida_env is None:
                msg = (
                    "ValidationError return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            frag = Fragment(value.template_name, value.block_name, **value.context)
            html = render_fragment(kida_env, frag)
            response = _html_response(html, intent="fragment").with_status(422)
            if value.retarget is not None:
                response = response.with_hx_retarget(value.retarget)
            return response
        case OOB():
            if kida_env is None:
                msg = (
                    "OOB return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            # Render the primary fragment/template
            main_response = negotiate(value.main, kida_env=kida_env, request=request)
            parts: list[str] = [main_response.text if isinstance(main_response, Response) else ""]
            # Render each OOB fragment and wrap with hx-swap-oob
            for frag in value.oob_fragments:
                html = render_fragment(kida_env, frag)
                target_id = frag.target if frag.target is not None else frag.block_name
                parts.append(f'<div id="{target_id}" hx-swap-oob="true">{html}</div>')
            body = "\n".join(parts)
            return _html_response(body, intent="fragment")
        case Stream():
            if kida_env is None:
                msg = (
                    "Stream return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
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
            if kida_env is None:
                msg = (
                    "TemplateStream return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            tmpl = kida_env.get_template(value.template_name)
            chunks = tmpl.render_stream_async(**value.context)
            return StreamingResponse(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
            )
        case LayoutSuspense():
            if kida_env is None:
                msg = (
                    "LayoutSuspense return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            req = value.request if value.request is not None else request
            is_htmx = bool(req and req.is_fragment)
            chunks = render_suspense(
                kida_env,
                value.suspense,
                is_htmx=is_htmx,
                layout_chain=value.layout_chain,
                layout_context=value.context,
                request=req,
            )
            if _should_append_streamed_shell_actions_oob(value.context, req):
                chunks = _append_shell_actions_oob_stream(chunks, value.context, kida_env)
            return StreamingResponse(
                chunks=chunks,
                content_type="text/html; charset=utf-8",
            )
        case Suspense():
            if kida_env is None:
                msg = (
                    "Suspense return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            is_htmx = request is not None and request.is_fragment
            chunks = render_suspense(kida_env, value, is_htmx=is_htmx)
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
            return Response(
                body=json_module.dumps(value, default=str),
                content_type="application/json; charset=utf-8",
            )
        case (inner, int() as status):
            response = negotiate(inner, kida_env=kida_env, request=request)
            if isinstance(response, Response):
                return response.with_status(status)
            return response
        case (inner, int() as status, dict() as headers):
            response = negotiate(inner, kida_env=kida_env, request=request)
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


def _render_shell_actions_oob(context: dict[str, Any], kida_env: Environment) -> str:
    """Render shell action OOB markup for boosted layout navigations."""
    from kida.environment.exceptions import TemplateNotFoundError

    actions = normalize_shell_actions(context.get(SHELL_ACTIONS_CONTEXT_KEY))
    fragment = shell_actions_fragment(actions)
    if fragment is None or actions is None:
        target = SHELL_ACTIONS_TARGET
        html = ""
    else:
        template_name, block_name, target = fragment
        try:
            html = render_fragment(
                kida_env,
                Fragment(template_name, block_name, shell_actions=actions),
            )
        except TemplateNotFoundError:
            html = ""
    return f'<div id="{target}" hx-swap-oob="innerHTML">{html}</div>'


async def _append_shell_actions_oob_stream(
    chunks: AsyncIterator[str],
    context: dict[str, Any],
    kida_env: Environment,
) -> AsyncIterator[str]:
    """Append shell action OOB markup to the first streamed chunk."""
    first_chunk = True
    oob = _render_shell_actions_oob(context, kida_env)
    async for chunk in chunks:
        if first_chunk:
            yield "\n".join((chunk, oob))
            first_chunk = False
            continue
        yield chunk
    if first_chunk:
        yield oob


def _should_append_streamed_shell_actions_oob(
    context: dict[str, Any],
    request: Request | None,
) -> bool:
    """Whether a streamed layout response should refresh shell actions via OOB."""
    del context
    if request is None:
        return False
    return (
        request.is_fragment
        and not request.is_history_restore
        and request.is_boosted
    )
