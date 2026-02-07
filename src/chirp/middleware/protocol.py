"""Middleware protocol and Next type alias.

A middleware is any callable matching::

    async def my_mw(request: Request, next: Next) -> Response: ...

No base class required. The framework checks the shape, not the lineage.
"""

from collections.abc import Awaitable, Callable
from typing import Protocol

from chirp.http.request import Request
from chirp.http.response import Response

# The next handler in the middleware chain
type Next = Callable[[Request], Awaitable[Response]]


class Middleware(Protocol):
    """Protocol for chirp middleware.

    Accepts both functions and callable objects::

        # Function middleware
        async def timing(request: Request, next: Next) -> Response:
            start = time.monotonic()
            response = await next(request)
            elapsed = time.monotonic() - start
            return response.with_header("X-Time", f"{elapsed:.3f}")

        # Class middleware
        class RateLimiter:
            async def __call__(self, request: Request, next: Next) -> Response:
                ...
    """

    async def __call__(self, request: Request, next: Next) -> Response: ...
