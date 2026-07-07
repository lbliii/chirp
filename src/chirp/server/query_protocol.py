"""HTTP QUERY request and response protocol enforcement."""

from typing import Any

from chirp.errors import HTTPError
from chirp.http.query_media import (
    query_content_type_supported,
    response_content_type_acceptable,
    serialize_accept_query,
)
from chirp.http.request import Request
from chirp.routing.route import Route

QUERY_ACCEPT_HEADER_CACHE_KEY = "_chirp_query_accept"


def _accept_query_header(route: Route) -> tuple[tuple[str, str], ...]:
    supported = route.query_media_types or ()
    return (("Accept-Query", serialize_accept_query(supported)),)


def validate_query_request(route: Route, request: Request) -> None:
    """Reject malformed or unsupported QUERY content before handler invocation."""
    if request.method != "QUERY":
        return
    supported = route.query_media_types or ()
    request._cache[QUERY_ACCEPT_HEADER_CACHE_KEY] = serialize_accept_query(supported)
    content_type = request.content_type
    if content_type is None or not content_type.strip():
        raise HTTPError(
            400,
            f"QUERY route {route.path!r} requires a Content-Type header; "
            f"supported media types: {', '.join(supported)}.",
            _accept_query_header(route),
        )
    try:
        is_supported = query_content_type_supported(content_type, supported)
    except (TypeError, ValueError) as exc:
        raise HTTPError(
            400,
            f"QUERY route {route.path!r} received malformed Content-Type {content_type!r}: {exc}.",
            _accept_query_header(route),
        ) from exc
    if not is_supported:
        raise HTTPError(
            415,
            f"QUERY route {route.path!r} does not support Content-Type "
            f"{content_type!r}; expected one of: {', '.join(supported)}.",
            _accept_query_header(route),
        )


def validate_query_response(route: Route, request: Request, response: Any) -> None:
    """Reject a negotiated QUERY representation that cannot satisfy Accept."""
    if request.method != "QUERY":
        return
    accept = request.headers.get("accept")
    if accept is None or not accept.strip():
        return
    content_type = getattr(response, "content_type", None)
    if not isinstance(content_type, str) or not response_content_type_acceptable(
        content_type, accept
    ):
        selected = content_type if isinstance(content_type, str) else "<missing>"
        raise HTTPError(
            406,
            f"QUERY route {route.path!r} selected response media type "
            f"{selected!r}, which does not satisfy Accept {accept!r}.",
            _accept_query_header(route),
        )
