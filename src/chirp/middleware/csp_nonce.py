"""CSP nonce middleware — per-request nonce for Content-Security-Policy.

Generates a cryptographically random nonce per request, stores it in a
ContextVar, and injects it into the CSP header on the way out.
"""

import dataclasses
import secrets
from contextvars import ContextVar, Token

from chirp.http.request import Request
from chirp.http.response import Response, StreamingResponse
from chirp.middleware.protocol import AnyResponse, Next

_csp_nonce_var: ContextVar[str] = ContextVar("chirp_csp_nonce")


def _set_csp_nonce(value: str) -> Token:
    """Set the request-scoped CSP nonce ContextVar, returning its reset token.

    Internal helper so :mod:`chirp.server.sender` can re-establish the nonce
    while a ``StreamingResponse`` generator drains, without importing the
    middleware class (keeps the server -> middleware layering one-directional,
    mirroring ``request_var`` usage).
    """
    return _csp_nonce_var.set(value)


def _reset_csp_nonce(token: Token) -> None:
    """Reset the CSP nonce ContextVar from a token returned by :func:`_set_csp_nonce`."""
    _csp_nonce_var.reset(token)


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

    __slots__ = ("_base_csp", "_script_origins", "_unsafe_eval")

    def __init__(self, base_csp: str | None = None, *, unsafe_eval: bool = False) -> None:
        self._base_csp = base_csp or (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
        )
        self._script_origins = "https://unpkg.com https://cdn.jsdelivr.net"
        self._unsafe_eval = unsafe_eval

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
                eval_token = " 'unsafe-eval'" if self._unsafe_eval else ""
                csp = f"{self._base_csp}; script-src 'self'{eval_token} 'nonce-{nonce}' {self._script_origins}"
                response = response.with_header("Content-Security-Policy", csp)
                if isinstance(response, StreamingResponse):
                    # Carry the live nonce onto the streaming response so the
                    # sender can re-establish it while the generator drains —
                    # this finally resets the var the instant next() returns,
                    # which is *before* any Suspense chunk is produced.
                    response = dataclasses.replace(response, csp_nonce=nonce)
            return response
        finally:
            _csp_nonce_var.reset(token)
