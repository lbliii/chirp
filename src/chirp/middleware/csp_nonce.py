"""CSP nonce middleware — per-request nonce for Content-Security-Policy.

Generates a cryptographically random nonce per request, stores it in a
ContextVar, and injects it into the CSP header on the way out.
"""

import dataclasses
import secrets
from contextvars import ContextVar, Token
from typing import Any, ClassVar

from chirp.http.request import Request
from chirp.http.response import FileResponse, Response, StreamingResponse
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

    template_globals: ClassVar[dict[str, Any]] = {"csp_nonce": csp_nonce}

    __slots__ = ("_base_csp", "_script_origins", "_style_unsafe_inline", "_unsafe_eval")

    def __init__(
        self,
        base_csp: str | None = None,
        *,
        unsafe_eval: bool = False,
        style_unsafe_inline: bool = False,
    ) -> None:
        self._base_csp = base_csp or (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
        )
        self._script_origins = "https://unpkg.com https://cdn.jsdelivr.net"
        self._unsafe_eval = unsafe_eval
        # Alpine's x-show writes inline `style="display:none"` attributes that
        # cannot be nonced; the only way to permit them is style-src
        # 'unsafe-inline'. Scoped to style-src only — script-src stays nonce-only
        # (+ 'unsafe-eval' when needed). Set by the compiler for Alpine apps.
        self._style_unsafe_inline = style_unsafe_inline

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        nonce = secrets.token_urlsafe(22)
        token = _csp_nonce_var.set(nonce)
        try:
            response = await next(request)
            # FileResponse included so static HTML files served through the
            # middleware stack still receive the per-request nonce CSP header.
            if isinstance(response, (Response, StreamingResponse, FileResponse)):
                eval_token = " 'unsafe-eval'" if self._unsafe_eval else ""
                style_token = (
                    "; style-src 'self' 'unsafe-inline'" if self._style_unsafe_inline else ""
                )
                csp = (
                    f"{self._base_csp}; "
                    f"script-src 'self'{eval_token} 'nonce-{nonce}' {self._script_origins}"
                    f"{style_token}"
                )
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
