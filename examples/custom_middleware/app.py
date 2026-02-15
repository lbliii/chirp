"""Custom Middleware — function and class middleware examples.

Runnable version of the custom middleware docs. Demonstrates:
- Function middleware (timing — adds X-Response-Time header)
- Class middleware (rate limiter — 5 req/min per IP, returns 429 when exceeded)
- threading.Lock for thread-safe shared state (free-threading)

Run:
    cd examples/custom_middleware && python app.py
"""

import asyncio
import threading
import time
from typing import Any

from chirp import App, Request, Response
from chirp.middleware.protocol import Next

app = App()


# ---------------------------------------------------------------------------
# Function middleware — timing
# ---------------------------------------------------------------------------


async def timing(request: Request, next: Next) -> Response:
    """Add X-Response-Time header to every response."""
    start = time.monotonic()
    response = await next(request)
    elapsed = time.monotonic() - start
    if isinstance(response, Response):
        return response.with_header("X-Response-Time", f"{elapsed:.3f}s")
    return response


# ---------------------------------------------------------------------------
# Class middleware — rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Per-IP rate limiter. Returns 429 when limit exceeded."""

    def __init__(self, max_requests: int, window: float) -> None:
        self.max_requests = max_requests
        self.window = window
        self._counts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    async def __call__(self, request: Request, next: Next) -> Any:
        # Use X-Forwarded-For if behind a proxy; else a simple client identifier
        client_ip = request.headers.get("x-forwarded-for", "127.0.0.1")
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        with self._lock:
            now = time.monotonic()
            hits = self._counts.setdefault(client_ip, [])
            hits[:] = [t for t in hits if now - t < self.window]

            if len(hits) >= self.max_requests:
                return Response("Too Many Requests").with_status(429)
            hits.append(now)

        return await next(request)


# ---------------------------------------------------------------------------
# Middleware stack (order: last added runs first on request)
# ---------------------------------------------------------------------------

app.add_middleware(RateLimiter(max_requests=5, window=60.0))
app.add_middleware(timing)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Simple OK response."""
    return "OK"


@app.route("/slow")
async def slow():
    """Delayed response — verifies timing header."""
    await asyncio.sleep(0.1)
    return "OK"


if __name__ == "__main__":
    app.run()
