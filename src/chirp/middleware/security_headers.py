"""Security headers middleware — X-Frame-Options, X-Content-Type-Options, Referrer-Policy.

Adds common security headers to HTML responses per HTML Living Standard
recommendations (clickjacking, MIME sniffing, referrer leakage).

Headers are applied only to text/html responses. Skipped for JSON, SSE,
static files, and other non-HTML content types.
"""

from dataclasses import dataclass

from chirp.http.request import Request
from chirp.http.response import Response, SSEResponse, StreamingResponse
from chirp.middleware.protocol import AnyResponse, Next


@dataclass(frozen=True, slots=True)
class SecurityHeadersConfig:
    """Configuration for security headers.

    All values are applied as-is. Use standard header values.
    """

    x_frame_options: str = "DENY"
    x_content_type_options: str = "nosniff"
    referrer_policy: str = "strict-origin-when-cross-origin"
    content_security_policy: str | None = (
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
    )
    strict_transport_security: str | None = None


def _is_html_response(response: AnyResponse) -> bool:
    """True if response is HTML and should receive security headers."""
    if isinstance(response, SSEResponse):
        return False
    ct = getattr(response, "content_type", "") or ""
    return ct.startswith("text/html")


def _add_headers(response: Response | StreamingResponse, config: SecurityHeadersConfig) -> AnyResponse:
    """Add security headers to a Response or StreamingResponse."""
    secured = (
        response.with_header("X-Frame-Options", config.x_frame_options)
        .with_header("X-Content-Type-Options", config.x_content_type_options)
        .with_header("Referrer-Policy", config.referrer_policy)
    )
    if config.content_security_policy:
        secured = secured.with_header("Content-Security-Policy", config.content_security_policy)
    if config.strict_transport_security:
        secured = secured.with_header(
            "Strict-Transport-Security", config.strict_transport_security
        )
    return secured


class SecurityHeadersMiddleware:
    """Add security headers to HTML responses.

    Per HTML spec recommendations:
    - X-Frame-Options — prevents clickjacking
    - X-Content-Type-Options — prevents MIME sniffing
    - Referrer-Policy — controls referrer leakage

    Usage::

        from chirp.middleware import SecurityHeadersMiddleware

        app.add_middleware(SecurityHeadersMiddleware())

    Or with custom config::

        from chirp.middleware.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        app.add_middleware(SecurityHeadersMiddleware(SecurityHeadersConfig(
            x_frame_options="SAMEORIGIN",
        )))
    """

    __slots__ = ("config",)

    def __init__(self, config: SecurityHeadersConfig | None = None) -> None:
        self.config = config or SecurityHeadersConfig()

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if not _is_html_response(response):
            return response
        if isinstance(response, (Response, StreamingResponse)):
            return _add_headers(response, self.config)
        return response
