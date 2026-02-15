"""Middleware — Protocol-based, no inheritance required.

A middleware is any callable matching:
    async def mw(request: Request, next: Next) -> Response

Built-in middleware:
    AuthMiddleware -- Dual-mode authentication (session + token)
    CORSMiddleware -- Cross-Origin Resource Sharing
    CSRFMiddleware -- CSRF token protection (requires SessionMiddleware)
    HTMLInject -- Inject snippets into HTML responses
    SecurityHeadersMiddleware -- X-Frame-Options, X-Content-Type-Options, Referrer-Policy
    SessionMiddleware -- Signed cookie sessions (requires itsdangerous)
    StaticFiles -- Serve static files from a directory
"""

from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.builtin import CORSConfig, CORSMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.inject import HTMLInject
from chirp.middleware.protocol import Middleware, Next
from chirp.middleware.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)
from chirp.middleware.static import StaticFiles

__all__ = [
    "AuthConfig",
    "AuthMiddleware",
    "CORSConfig",
    "CORSMiddleware",
    "CSRFConfig",
    "CSRFMiddleware",
    "HTMLInject",
    "Middleware",
    "Next",
    "SecurityHeadersConfig",
    "SecurityHeadersMiddleware",
    "StaticFiles",
]
