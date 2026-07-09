"""Shared conditional-response evaluation for GET, HEAD, and QUERY."""

from dataclasses import replace
from email.utils import parsedate_to_datetime

from chirp.http.request import Request
from chirp.http.response import Response


def has_nonce_csp_html(response: Response) -> bool:
    """Return whether an HTML response carries a nonce-based CSP.

    A per-request CSP nonce makes the final HTML representation unsafe to
    reuse through ``304 Not Modified``: the browser could combine a cached
    body containing nonce A with a newly generated policy containing nonce B.
    """
    if "text/html" not in response.content_type.lower():
        return False
    return any(
        name.lower() == "content-security-policy" and "'nonce-" in value.lower()
        for name, value in response.headers
    )


def parse_http_date(value: str) -> float | None:
    """Parse an HTTP-date header into a POSIX timestamp, or None if invalid."""
    try:
        return parsedate_to_datetime(value).timestamp()
    except TypeError, ValueError, IndexError, OverflowError:
        return None


def etag_matches(if_none_match: str, etag: str) -> bool:
    """Apply RFC 9110 weak comparison for If-None-Match."""
    if_none_match = if_none_match.strip()
    if if_none_match == "*":
        return True
    bare = etag[2:] if etag.startswith("W/") else etag
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        candidate_bare = candidate[2:] if candidate.startswith("W/") else candidate
        if candidate_bare == bare:
            return True
    return False


def _strong_etag_matches(if_match: str, etag: str) -> bool:
    """Apply RFC 9110 strong comparison for If-Match."""
    if if_match.strip() == "*":
        return True
    if etag.startswith("W/"):
        return False
    return any(
        candidate.strip() == etag and not candidate.strip().startswith("W/")
        for candidate in if_match.split(",")
    )


def evaluate_conditional_response(request: Request, response: Response) -> Response:
    """Return 304 when request validators match an ordinary representation."""
    if request.method not in {"GET", "HEAD", "QUERY"} or response.status != 200:
        return response

    etag = response.header("ETag")
    if_match = request.headers.get("if-match")
    if if_match is not None:
        if etag is None:
            if if_match.strip() != "*":
                return replace(response, body=b"", status=412)
        elif not _strong_etag_matches(if_match, etag):
            return replace(response, body=b"", status=412)
    else:
        last_modified = response.header("Last-Modified")
        if_unmodified_since = request.headers.get("if-unmodified-since")
        if last_modified is not None and if_unmodified_since is not None:
            representation_time = parse_http_date(last_modified)
            request_time = parse_http_date(if_unmodified_since)
            if (
                representation_time is not None
                and request_time is not None
                and int(representation_time) > int(request_time)
            ):
                return replace(response, body=b"", status=412)

    # A nonce-bearing HTML body changes on every request even when an
    # application-supplied source validator is unchanged. Preserve validators
    # for diagnostics and source identity, but never let them reuse bytes that
    # were rendered under a different CSP nonce.
    if has_nonce_csp_html(response):
        return response

    if_none_match = request.headers.get("if-none-match")
    if if_none_match is not None:
        if if_none_match.strip() == "*" or (etag is not None and etag_matches(if_none_match, etag)):
            return response.with_status(304)
        return response

    last_modified = response.header("Last-Modified")
    if_modified_since = request.headers.get("if-modified-since")
    if last_modified is None or if_modified_since is None:
        return response
    representation_time = parse_http_date(last_modified)
    request_time = parse_http_date(if_modified_since)
    if (
        representation_time is not None
        and request_time is not None
        and int(representation_time) <= int(request_time)
    ):
        return response.with_status(304)
    return response
