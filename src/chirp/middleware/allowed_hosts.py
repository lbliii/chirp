"""Allowed hosts middleware — reject requests with unrecognized Host header.

Validates the Host header against a whitelist. Wildcard ``".example.com"``
matches subdomains. ``"*"`` allows all hosts (dev default).
"""

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next


class AllowedHostsMiddleware:
    """Reject requests whose Host header does not match allowed_hosts.

    Usage::

        from chirp.middleware.allowed_hosts import AllowedHostsMiddleware

        app.add_middleware(AllowedHostsMiddleware(("example.com", ".example.com")))
    """

    __slots__ = ("_allow_all", "_debug", "_hosts")

    def __init__(
        self,
        allowed_hosts: tuple[str, ...] = ("*",),
        *,
        debug: bool = False,
    ) -> None:
        self._allow_all = "*" in allowed_hosts
        self._hosts = allowed_hosts
        self._debug = debug

    def _is_valid_host(self, host: str) -> bool:
        if self._allow_all:
            return True
        # Strip port
        if ":" in host:
            host = host.rsplit(":", 1)[0]
        host = host.lower()
        for pattern in self._hosts:
            pattern = pattern.lower()
            if pattern == host:
                return True
            # ".example.com" matches sub.example.com and example.com
            if pattern.startswith(".") and (host == pattern[1:] or host.endswith(pattern)):
                    return True
        return False

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        host = request.headers.get("host", "") or ""
        if not self._is_valid_host(host):
            body = "Invalid HTTP_HOST header"
            if self._debug:
                body = f"Invalid HTTP_HOST header: {host!r}. Allowed: {self._hosts}"
            return Response(body, status=400, content_type="text/plain")
        return await next(request)
