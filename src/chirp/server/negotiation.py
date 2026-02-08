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
from chirp.templating.returns import Fragment, Page, Stream, Template, ValidationError
from chirp.templating.streaming import has_async_context, render_stream_async

if TYPE_CHECKING:
    from chirp.http.request import Request


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
    6. ``ValidationError``  -> Fragment + 422 + optional HX-Retarget
    7. ``Stream``           -> kida render_stream() -> StreamingResponse
                               (async sources resolved concurrently)
    8. ``EventStream``      -> SSEResponse (handler dispatches to SSE)
    9. ``str``              -> 200, text/html
    10. ``bytes``           -> 200, application/octet-stream
    11. ``dict`` / ``list`` -> 200, application/json
    12. ``(value, int)``    -> negotiate value, override status
    13. ``(value, int, dict)`` -> negotiate value, override status + headers
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
            return Response(body=html, content_type="text/html; charset=utf-8")
        case Fragment():
            if kida_env is None:
                msg = (
                    "Fragment return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise ConfigurationError(msg)
            html = render_fragment(kida_env, value)
            return Response(body=html, content_type="text/html; charset=utf-8")
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
            else:
                tpl = Template(value.name, **value.context)
                html = render_template(kida_env, tpl)
            return Response(body=html, content_type="text/html; charset=utf-8")
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
            ).with_status(422)
            if value.retarget is not None:
                response = response.with_hx_retarget(value.retarget)
            return response
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
            return Response(body=value, content_type="text/html; charset=utf-8")
        case bytes():
            return Response(body=value, content_type="application/octet-stream")
        case dict() | list():
            return Response(
                body=json_module.dumps(value, default=str),
                content_type="application/json; charset=utf-8",
            )
        case (inner, int() as status):
            response = negotiate(inner, kida_env=kida_env)
            if isinstance(response, Response):
                return response.with_status(status)
            return response
        case (inner, int() as status, dict() as headers):
            response = negotiate(inner, kida_env=kida_env)
            if isinstance(response, Response):
                return response.with_status(status).with_headers(headers)
            return response
        case _:
            msg = (
                f"Cannot convert {type(value).__name__} to a response. "
                f"Return str, dict, bytes, Template, Fragment, Stream, "
                f"EventStream, Response, or Redirect."
            )
            raise TypeError(msg)
