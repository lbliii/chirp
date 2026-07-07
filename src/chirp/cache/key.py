"""Cache key derivation — Vary-header-aware, pluggable key functions."""

import hashlib
import re
from collections.abc import Iterable
from typing import Any

from chirp.http.request import Request

_QUERY_CACHE_KEY_PREFIX = "chirp:query:v1:"
_PRIVATE_REQUEST_HEADERS = ("cookie", "authorization")
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def default_cache_key(request: Request) -> str:
    """Derive a cache key from the request.

    Includes URL query and htmx response shape so full-page, fragment,
    boosted, and history-restore responses cannot masquerade as each other.

    Format: ``chirp:{method}:{path}:{hash(inputs)}``
    """
    parts = [
        request.method,
        request.path,
        _raw_query_string(request),
        f"hx={int(bool(getattr(request, 'is_htmx', False)))}",
        f"boost={int(bool(getattr(request, 'is_boosted', False)))}",
        f"history={int(bool(getattr(request, 'is_history_restore', False)))}",
        f"target={getattr(request, 'htmx_target_id', None) or ''}",
    ]
    raw = "|".join(parts)
    h = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"chirp:{request.method}:{request.path}:{h}"


def _raw_query_string(request: Request) -> str:
    query = getattr(request, "query", None)
    raw = getattr(query, "_raw", None)
    if isinstance(raw, bytes):
        return raw.decode("latin-1")
    if raw is not None:
        return str(raw)
    return str(getattr(request, "query_string", ""))


def vary_aware_cache_key(request: Request, vary_headers: tuple[str, ...] = ()) -> str:
    """Cache key that includes Vary header values for differentiation."""
    base = default_cache_key(request)
    if not vary_headers:
        return base
    vary_parts = []
    for header in sorted(vary_headers):
        val = request.headers.get(header.lower(), "")
        vary_parts.append(f"{header}={val}")
    vary_hash = hashlib.md5("|".join(vary_parts).encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{base}:{vary_hash}"


async def query_cache_key(
    request: Request,
    vary_headers: tuple[str, ...] = (),
) -> str:
    """Return an opaque, body-aware cache key for one QUERY request.

    This function only designs the key; :class:`CacheMiddleware` continues to
    bypass QUERY until its separate explicit opt-in lands. It reads the body
    through :meth:`Request.body`, so the existing request limit is enforced and
    the exact bytes remain cached for the handler. Call it before any direct
    iteration of ``request.stream()``.

    Every selected-representation input is length-framed into SHA-256. Raw body,
    URI, and header values never appear in the returned key. Content metadata is
    intentionally exact: semantic media-type normalization remains a separate,
    media-specific opt-in.

    Requests carrying Cookie or Authorization are ineligible rather than keyed;
    this preserves CacheMiddleware's private-request bypass boundary.
    """
    if request.method != "QUERY":
        raise ValueError(
            f"query_cache_key requires request.method == 'QUERY', got {request.method!r}"
        )
    private_header = next(
        (name for name in _PRIVATE_REQUEST_HEADERS if any(request.headers.get_list(name))),
        None,
    )
    if private_header is not None:
        raise ValueError(
            f"query_cache_key is unavailable when {private_header.title()} is present; "
            "private requests must bypass shared response caching"
        )

    normalized_vary = _normalize_vary_headers(vary_headers)
    body = await request.body()
    digest = hashlib.sha256()
    _hash_field(digest, b"method", request.method.encode("ascii"))
    _hash_field(digest, b"path", request.path.encode("utf-8", errors="surrogatepass"))
    _hash_field(digest, b"uri-query", _raw_query_bytes(request))
    _hash_field(digest, b"body", body)
    _hash_header(digest, request, "content-type")
    _hash_header(digest, request, "content-encoding")
    _hash_header(digest, request, "accept")
    _hash_field(digest, b"htmx", _bool_bytes(request.is_htmx))
    _hash_field(digest, b"htmx-boosted", _bool_bytes(request.is_boosted))
    _hash_field(digest, b"htmx-history", _bool_bytes(request.is_history_restore))
    _hash_field(
        digest,
        b"htmx-target",
        (request.htmx_target_id or "").encode("utf-8", errors="surrogatepass"),
    )
    _hash_field(
        digest,
        b"htmx-partial",
        (request.htmx_partial or "").encode("utf-8", errors="surrogatepass"),
    )
    _hash_field(digest, b"vary-count", str(len(normalized_vary)).encode("ascii"))
    for name in normalized_vary:
        encoded_name = name.encode("ascii")
        _hash_field(digest, b"vary-name", encoded_name)
        _hash_header(digest, request, name, label=b"vary-value:" + encoded_name)
    return _QUERY_CACHE_KEY_PREFIX + digest.hexdigest()


def _normalize_vary_headers(vary_headers: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for header in vary_headers:
        if not isinstance(header, str):
            raise TypeError("QUERY cache vary header names must be strings")
        name = header.strip().lower()
        if not name:
            raise ValueError("QUERY cache vary header names cannot be empty")
        if not _HEADER_NAME_RE.fullmatch(name):
            raise ValueError(f"invalid QUERY cache vary header name: {header!r}")
        normalized.add(name)
    return tuple(sorted(normalized))


def _hash_header(
    digest: Any,
    request: Request,
    name: str,
    *,
    label: bytes | None = None,
) -> None:
    values = request.headers.get_list(name)
    field_label = label or b"header:" + name.encode("ascii")
    _hash_field(digest, field_label + b":count", str(len(values)).encode("ascii"))
    for value in values:
        _hash_field(digest, field_label, value.encode("latin-1"))


def _hash_field(digest: Any, label: bytes, value: bytes) -> None:
    """Hash one unambiguous label/value frame without copying request content."""
    digest.update(len(label).to_bytes(2, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _bool_bytes(value: bool) -> bytes:
    return b"1" if value else b"0"


def _raw_query_bytes(request: Request) -> bytes:
    query = getattr(request, "query", None)
    raw = getattr(query, "_raw", None)
    if isinstance(raw, bytes):
        return raw
    if raw is not None:
        return str(raw).encode("utf-8", errors="surrogatepass")
    fallback = getattr(request, "query_string", "")
    if isinstance(fallback, bytes):
        return fallback
    return str(fallback).encode("utf-8", errors="surrogatepass")
