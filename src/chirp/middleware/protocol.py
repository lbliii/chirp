"""Middleware protocol and Next type alias.

A middleware is any callable matching::

    async def my_mw(request: Request, next: Next) -> AnyResponse: ...

No base class required. The framework checks the shape, not the lineage.

The ``next`` callable may return ``Response``, ``StreamingResponse``,
or ``SSEResponse``.  All three share the ``.with_header()`` /
``.with_status()`` chainable API, so middleware can modify them
uniformly.
"""

from collections.abc import Awaitable, Callable
from typing import Protocol

from chirp.http.request import Request
from chirp.http.response import Response, SSEResponse, StreamingResponse

# Any response type the pipeline can produce
type AnyResponse = Response | StreamingResponse | SSEResponse

# The next handler in the middleware chain
type Next = Callable[[Request], Awaitable[AnyResponse]]


class Middleware(Protocol):
    """Protocol for chirp middleware.

    Accepts both functions and callable objects::

        # Function middleware
        async def timing(request: Request, next: Next) -> AnyResponse:
            start = time.monotonic()
            response = await next(request)
            elapsed = time.monotonic() - start
            return response.with_header("X-Time", f"{elapsed:.3f}")

        # Class middleware
        class RateLimiter:
            async def __call__(self, request: Request, next: Next) -> AnyResponse:
                ...
    """

    async def __call__(self, request: Request, next: Next) -> AnyResponse: ...
