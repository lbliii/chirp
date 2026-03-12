"""Lightweight SyncRequest for the fused sync path.

Minimal request wrapper for handle_sync(). Only method and path are decoded
eagerly; query, cookies, and headers are lazy via cached_property.
"""

from __future__ import annotations

from functools import cached_property

from chirp.http.cookies import parse_cookies
from chirp.http.headers import Headers
from chirp.http.query import QueryParams


def _raw_request_type() -> type:
    """Lazy import to avoid circular dependency with pounce."""
    from pounce.sync_protocol import RawRequest

    return RawRequest


class SyncRequest:
    """Minimal request for the fused sync path.

    Only method and path are decoded eagerly. Query, cookies, and headers
    are lazy — only parsed when accessed.
    """

    __slots__ = ("__dict__", "_raw", "method", "path", "path_params")

    def __init__(
        self,
        method: str,
        path: str,
        _raw: object,
        path_params: dict[str, str] | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.path_params = path_params or {}
        self._raw = _raw

    @cached_property
    def query(self) -> QueryParams:
        raw = self._raw
        if hasattr(raw, "query_string"):
            return QueryParams(getattr(raw, "query_string", b""))
        return QueryParams(b"")

    @cached_property
    def cookies(self) -> dict[str, str]:
        raw = self._raw
        if hasattr(raw, "headers"):
            cookie_val = _get_header_bytes(getattr(raw, "headers", ()), b"cookie")
            if cookie_val:
                return parse_cookies(cookie_val.decode("latin-1"))
        return {}

    @cached_property
    def headers(self) -> Headers:
        raw = self._raw
        if hasattr(raw, "headers"):
            return Headers(getattr(raw, "headers", ()))
        return Headers(())


def _get_header_bytes(headers: tuple[tuple[bytes, bytes], ...], name: bytes) -> bytes | None:
    """Get a header value by lowercase name."""
    name_lower = name.lower()
    for hname, hvalue in headers:
        if hname.lower() == name_lower:
            return hvalue
    return None
