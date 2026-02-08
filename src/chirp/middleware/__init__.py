"""Middleware — Protocol-based, no inheritance required.

A middleware is any callable matching:
    async def mw(request: Request, next: Next) -> Response

Built-in middleware:
    CORSMiddleware -- Cross-Origin Resource Sharing
    HTMLInject -- Inject snippets into HTML responses
    StaticFiles -- Serve static files from a directory
    SessionMiddleware -- Signed cookie sessions (requires itsdangerous)
    CSRFMiddleware -- CSRF token protection (requires SessionMiddleware)
"""

from chirp.middleware.builtin import CORSConfig, CORSMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.inject import HTMLInject
from chirp.middleware.protocol import Middleware, Next
from chirp.middleware.static import StaticFiles

__all__ = [
    "CORSConfig",
    "CORSMiddleware",
    "CSRFConfig",
    "CSRFMiddleware",
    "HTMLInject",
    "Middleware",
    "Next",
    "StaticFiles",
]
