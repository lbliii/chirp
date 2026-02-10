"""Content negotiation — maps return values to Response objects.

The ContentNegotiator inspects the return value from a route handler
and produces the appropriate Response. isinstance-based dispatch,
no magic, fully predictable.
"""

import json as json_module
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp.errors import ConfigurationError
from chirp.http.response import Redirect, Response, SSEResponse, StreamingResponse
from chirp.realtime.events import EventStream
from chirp.templating.integration import render_fragment, render_template
from chirp.templating.returns import (
    OOB,
    Action,
    Fragment,
    InlineTemplate,
    LayoutPage,
    Page,
    Stream,
    Template,
    ValidationError,
)
from chirp.templating.streaming import has_async_context, render_stream_async

if TYPE_CHECKING:
    from chirp.http.request import Request


def _minimal_kida_env() -> Environment:
    """Create a bare kida Environment for inline template rendering.

    Used when no template_dir is configured but an InlineTemplate
    needs to be rendered (prototyping without any file templates).
    """
    return Environment()


def _html_response(body: str, *, intent: str) -> Response:
    """Build a text/html response with explicit render intent."""
    return Response(
        body=body,
        content_type="text/html; charset=utf-8",
        render_intent=intent,
    )


def negotiate(
    value: Any,
    *,
    kida_env: Environment | None = None,
    request: Request | None = None,
) -> Response | StreamingResponse | SSEResponse:
    """Convert a route handler's return value to a Response.

    Dispatch order:

    1. ``Response``         -> pass through
    2. ``Redirect``         -> 302 with Location header
    3. ``Template``         -> render via kida -> Response
    4. ``Fragment``         -> render block via kida -> Response
    5. ``Page``             -> Template or Fragment based on request headers
    6. ``Action``           -> empty Response + optional HX headers
    7. ``ValidationError``  -> Fragment + 422 + optional HX-Retarget
    8. ``OOB``              -> primary + hx-swap-oob fragments
    9. ``Stream``           -> kida render_stream() -> StreamingResponse
                               (async sources resolved concurrently)
    10. ``EventStream``      -> SSEResponse (handler dispatches to SSE)
    11. ``str``             -> 200, text/html
    12. ``bytes``           -> 200, application/octet-stream
    13. ``dict`` / ``list`` -> 200, application/json
    14. ``(value, int)``    -> negotiate value, override status
    15. ``(value, int, dict)`` -> negotiate value, override status + headers
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
        case Page():
            if kida_env is None:
                msg = (
                    "Page return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            if (
                request is not None
                and request.is_fragment
                and not request.is_history_restore
            ):
                frag = Fragment(value.name, value.block_name, **value.context)
                html = render_fragment(kida_env, frag)
                intent = "fragment"
            else:
                tpl = Template(value.name, **value.context)
                html = render_template(kida_env, tpl)
                intent = "full_page"
            return _html_response(html, intent=intent)
        case LayoutPage():
            if kida_env is None:
                msg = (
                    "LayoutPage return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            html = _render_layout_page(value, kida_env, request)
            render_intent = (
                "fragment"
                if request is not None and request.is_fragment and not request.is_history_restore
                else "full_page"
            )
            return _html_response(html, intent=render_intent)
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
            response = Response(
                body=html, content_type="text/html; charset=utf-8"
            ).with_status(422).with_render_intent("fragment")
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
            parts: list[str] = [main_response.text if isinstance(main_response, Response)
                                else ""]
            # Render each OOB fragment and wrap with hx-swap-oob
            for frag in value.oob_fragments:
                html = render_fragment(kida_env, frag)
                target_id = frag.target if frag.target is not None else frag.block_name
                parts.append(
                    f'<div id="{target_id}" hx-swap-oob="true">{html}</div>'
                )
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
                f"Action, Stream, EventStream, Response, or Redirect."
            )
            raise TypeError(msg)


def _render_layout_page(
    value: LayoutPage,
    kida_env: Environment,
    request: Request | None,
) -> str:
    """Render a LayoutPage through its layout chain.

    Decides rendering depth based on request headers:

    - Fragment request (no history restore): render just the named block
    - Full page / history restore: render page block, then wrap with layouts
    - HX-Target present: render at the appropriate layout depth
    """
    from chirp.pages.renderer import render_with_layouts
    from chirp.pages.types import LayoutChain

    layout_chain: LayoutChain = value.layout_chain or LayoutChain()
    htmx_target: str | None = None
    is_fragment = False
    is_history_restore = False

    if request is not None:
        htmx_target = request.htmx_target
        is_fragment = request.is_fragment
        is_history_restore = request.is_history_restore

    # For pure fragment requests (no layouts involved), render just the block
    if is_fragment and not is_history_restore and not htmx_target:
        frag = Fragment(value.name, value.block_name, **value.context)
        return render_fragment(kida_env, frag)

    # Render the page's content block
    page_template = kida_env.get_template(value.name)
    page_html = page_template.render_block(value.block_name, value.context)

    # Compose with layout chain at the appropriate depth
    return render_with_layouts(
        kida_env,
        layout_chain=layout_chain,
        page_html=page_html,
        context=value.context,
        htmx_target=htmx_target,
        is_history_restore=is_history_restore,
    )
