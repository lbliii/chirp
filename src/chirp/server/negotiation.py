"""Content negotiation — maps return values to Response objects.

The ContentNegotiator inspects the return value from a route handler
and produces the appropriate Response. isinstance-based dispatch,
no magic, fully predictable.
"""

import json as json_module
from typing import Any

from kida import Environment

from chirp.http.response import Redirect, Response
from chirp.realtime.events import EventStream
from chirp.templating.integration import render_fragment, render_template
from chirp.templating.returns import Fragment, Stream, Template


def negotiate(value: Any, *, kida_env: Environment | None = None) -> Response:
    """Convert a route handler's return value to a Response.

    Dispatch order:

    1. ``Response``         -> pass through
    2. ``Redirect``         -> 302 with Location header
    3. ``Template``         -> render via kida -> Response
    4. ``Fragment``         -> render block via kida -> Response
    5. ``Stream``           -> placeholder (requires kida streaming, Phase 5)
    6. ``EventStream``      -> placeholder (SSE wired in Phase 6)
    7. ``str``              -> 200, text/html
    8. ``bytes``            -> 200, application/octet-stream
    9. ``dict`` / ``list``  -> 200, application/json
    10. ``(value, int)``    -> negotiate value, override status
    11. ``(value, int, dict)`` -> negotiate value, override status + headers
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
                raise RuntimeError(msg)
            html = render_template(kida_env, value)
            return Response(body=html, content_type="text/html; charset=utf-8")
        case Fragment():
            if kida_env is None:
                msg = (
                    "Fragment return type requires kida integration. "
                    "Ensure a template_dir is configured in AppConfig."
                )
                raise RuntimeError(msg)
            html = render_fragment(kida_env, value)
            return Response(body=html, content_type="text/html; charset=utf-8")
        case Stream():
            # Placeholder: streaming requires kida render_stream() (Phase 5)
            return Response(
                body=f"<!-- Stream: {value.template_name} -->",
                content_type="text/html; charset=utf-8",
            )
        case EventStream():
            # Placeholder: SSE requires ASGI streaming (Phase 6)
            return Response(
                body="",
                content_type="text/event-stream",
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
            return response.with_status(status)
        case (inner, int() as status, dict() as headers):
            response = negotiate(inner, kida_env=kida_env)
            return response.with_status(status).with_headers(headers)
        case _:
            msg = (
                f"Cannot convert {type(value).__name__} to a response. "
                f"Return str, dict, bytes, Template, Fragment, Stream, "
                f"EventStream, Response, or Redirect."
            )
            raise TypeError(msg)
