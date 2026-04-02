"""Cache key derivation — Vary-header-aware, pluggable key function."""

import hashlib

from chirp.http.request import Request


def default_cache_key(request: Request) -> str:
    """Derive a cache key from the request.

    Format: ``chirp:{method}:{path}:{hash(vary_headers)}``
    """
    parts = [request.method, request.path]
    raw = ":".join(parts)
    h = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"chirp:{request.method}:{request.path}:{h}"


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
