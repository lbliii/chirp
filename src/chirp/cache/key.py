"""Cache key derivation — Vary-header-aware, pluggable key function."""

import hashlib

from chirp.http.request import Request


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
