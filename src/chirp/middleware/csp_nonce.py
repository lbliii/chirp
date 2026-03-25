"""CSP nonce middleware — per-request nonce for Content-Security-Policy.

Generates a cryptographically random nonce per request, stores it in a
ContextVar, and injects it into the CSP header on the way out.
"""

import secrets
from contextvars import ContextVar

from chirp.http.request import Request
from chirp.http.response import Response, StreamingResponse
from chirp.middleware.protocol import AnyResponse, Next

_csp_nonce_var: ContextVar[str] = ContextVar("chirp_csp_nonce")


def get_csp_nonce() -> str:
    """Return the CSP nonce for the current request.

    Raises ``LookupError`` if called outside a request with CSP nonces enabled.
    """
    return _csp_nonce_var.get()


def csp_nonce() -> str:
    """Template global: ``{{ csp_nonce() }}`` for ``<script nonce="...">``.

    Returns empty string if nonces are not enabled (never breaks templates).
    """
    try:
        return _csp_nonce_var.get()
    except LookupError:
        return ""


class CSPNonceMiddleware:
    """Generate a per-request nonce and inject it into the CSP header.

    Usage::

        app.add_middleware(CSPNonceMiddleware())

    Then in templates::

        <script nonce="{{ csp_nonce() }}">...</script>
    """

    __slots__ = ("_base_csp",)

    def __init__(self, base_csp: str | None = None) -> None:
        self._base_csp = base_csp or (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
        )

    @property
    def template_globals(self) -> dict:
        """Expose csp_nonce() as a template global."""
        return {"csp_nonce": csp_nonce}

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        nonce = secrets.token_urlsafe(22)
        token = _csp_nonce_var.set(nonce)
        try:
            response = await next(request)
            if isinstance(response, (Response, StreamingResponse)):
                csp = f"{self._base_csp}; script-src 'self' 'nonce-{nonce}'"
                response = response.with_header("Content-Security-Policy", csp)
            return response
        finally:
            _csp_nonce_var.reset(token)
