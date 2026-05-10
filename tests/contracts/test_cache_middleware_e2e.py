"""End-to-end contract tests for ``CacheMiddleware``.

Sprint 4 of docs/plan-contract-tests-reliability.md. Drives every branch in
``src/chirp/cache/middleware.py:35`` through ``TestClient``:

- Cache miss then hit (the happy path)
- Non-GET requests bypass the cache entirely
- Responses with ``Set-Cookie`` are not cached (would leak per-user state)
- Non-200 responses are not cached
- Streaming/SSE responses are not cached (cannot replay)
- TTL expires and forces a refresh
- Backend ``get()`` exception is logged and degrades to handler invocation

Each test wires its own ``CacheMiddleware`` instance with a fresh
``MemoryCacheBackend`` so process-wide cache state cannot leak between tests
(per the risk-register mitigation in the plan).
"""

from __future__ import annotations

import asyncio

import pytest

from chirp.cache.backends.memory import MemoryCacheBackend
from chirp.cache.middleware import CacheMiddleware
from chirp.http.response import Response
from chirp.realtime.events import EventStream
from chirp.testing import TestClient
from tests.contracts._helpers import _app


def _wire_cache(app, backend=None, ttl: int = 300):
    """Attach a CacheMiddleware to *app* and return the backend used."""
    if backend is None:
        backend = MemoryCacheBackend()
    app.add_middleware(CacheMiddleware(backend, ttl=ttl))
    return backend


# ---------------------------------------------------------------------------
# 4.1 — Cache miss then hit
# ---------------------------------------------------------------------------


class TestCacheMissThenHit:
    """Two GETs to the same URL — handler runs once; second served from cache."""

    async def test_second_get_served_from_cache(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/cached")
        def cached():
            counter["calls"] += 1
            return f"<p>hit {counter['calls']}</p>"

        async with TestClient(app) as client:
            r1 = await client.get("/cached")
            r2 = await client.get("/cached")

        assert r1.status == 200
        assert r2.status == 200
        # Handler ran once — second request served from cache.
        assert counter["calls"] == 1
        # Both bodies are identical (the cached snapshot).
        assert r1.text == r2.text
        assert "hit 1" in r2.text

    async def test_distinct_query_strings_do_not_collide(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/threads")
        def threads(request):
            counter["calls"] += 1
            return f"<p>page {request.query.get('page')} call {counter['calls']}</p>"

        async with TestClient(app) as client:
            page_one = await client.get("/threads", query={"page": "1"})
            page_two = await client.get("/threads", query={"page": "2"})
            page_one_again = await client.get("/threads", query={"page": "1"})

        assert "page 1 call 1" in page_one.text
        assert "page 2 call 2" in page_two.text
        assert page_one_again.text == page_one.text
        assert counter["calls"] == 2

    async def test_htmx_and_full_page_shapes_do_not_collide(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/threads")
        def threads(request):
            counter["calls"] += 1
            shape = "fragment" if request.is_htmx else "full"
            return f"<p>{shape} call {counter['calls']}</p>"

        async with TestClient(app) as client:
            full = await client.get("/threads")
            fragment = await client.fragment("/threads", target="thread-list")
            full_again = await client.get("/threads")

        assert "full call 1" in full.text
        assert "fragment call 2" in fragment.text
        assert full_again.text == full.text
        assert counter["calls"] == 2


# ---------------------------------------------------------------------------
# 4.2 — Non-GET bypass
# ---------------------------------------------------------------------------


class TestNonGetBypass:
    """Non-GET methods bypass the cache entirely.

    ``middleware.py:36`` short-circuits before the backend is consulted —
    POST/PUT/DELETE responses are never stored or returned from cache.
    """

    async def test_post_runs_handler_every_time(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/x", methods=["POST"])
        def handler():
            counter["calls"] += 1
            return f"<p>{counter['calls']}</p>"

        async with TestClient(app) as client:
            await client.post("/x")
            await client.post("/x")

        assert counter["calls"] == 2


# ---------------------------------------------------------------------------
# 4.3 — Set-Cookie skip
# ---------------------------------------------------------------------------


class TestSetCookieSkip:
    """Responses carrying a ``Set-Cookie`` are never cached — both write paths.

    Caching a Set-Cookie response would replay one user's cookie to another.
    Two write paths exist: ``with_header("Set-Cookie", ...)`` writes to
    ``response.headers``; ``with_cookie(...)`` writes to a separate
    ``response.cookies`` tuple that ``sender.py`` flattens into Set-Cookie
    headers at wire time. The middleware must refuse both, otherwise the
    ``with_cookie`` path would silently cache the per-user cookie.
    """

    async def test_set_cookie_header_response_not_cached(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/login-header")
        def login():
            counter["calls"] += 1
            return Response(body=f"<p>{counter['calls']}</p>").with_header(
                "Set-Cookie", "session=abc; Path=/"
            )

        async with TestClient(app) as client:
            await client.get("/login-header")
            await client.get("/login-header")

        assert counter["calls"] == 2

    async def test_with_cookie_response_not_cached(self) -> None:
        """Regression: cookies set via ``with_cookie()`` must also skip caching.

        Before the fix, the middleware only checked ``response.headers`` for
        Set-Cookie. ``with_cookie()`` writes to ``response.cookies`` (flattened
        later by ``sender.py``), so per-user cookies were being cached and
        replayed to subsequent requesters.
        """
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/login-cookie")
        def login():
            counter["calls"] += 1
            return Response(body=f"<p>{counter['calls']}</p>").with_cookie(
                "session", "abc", path="/"
            )

        async with TestClient(app) as client:
            await client.get("/login-cookie")
            await client.get("/login-cookie")

        assert counter["calls"] == 2


class TestPrivateRequestBypass:
    """User-specific request headers bypass cache reads and writes."""

    async def test_cookie_request_not_cached(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/profile")
        def profile(request):
            counter["calls"] += 1
            return f"<p>{request.headers.get('cookie')}:{counter['calls']}</p>"

        async with TestClient(app) as client:
            first = await client.get("/profile", headers={"Cookie": "session=a"})
            second = await client.get("/profile", headers={"Cookie": "session=a"})
            anonymous = await client.get("/profile")
            anonymous_again = await client.get("/profile")

        assert counter["calls"] == 3
        assert first.text != second.text
        assert anonymous.text == anonymous_again.text

    async def test_authorization_request_not_cached(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/account")
        def account(request):
            counter["calls"] += 1
            return f"<p>{request.headers.get('authorization')}:{counter['calls']}</p>"

        async with TestClient(app) as client:
            first = await client.get("/account", headers={"Authorization": "Bearer a"})
            second = await client.get("/account", headers={"Authorization": "Bearer a"})

        assert counter["calls"] == 2
        assert first.text != second.text


# ---------------------------------------------------------------------------
# 4.4 — Non-200 skip
# ---------------------------------------------------------------------------


class TestNon200Skip:
    """Non-200 responses are never cached — error pages must stay fresh."""

    async def test_404_response_not_cached(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        @app.route("/missing")
        def missing():
            counter["calls"] += 1
            return Response(body="not here", status=404)

        async with TestClient(app) as client:
            r1 = await client.get("/missing")
            r2 = await client.get("/missing")

        assert r1.status == 404
        assert r2.status == 404
        # Handler ran twice — 404 was not cached.
        assert counter["calls"] == 2


# ---------------------------------------------------------------------------
# 4.5 — Streaming / SSE bypass
# ---------------------------------------------------------------------------


class TestStreamingBypass:
    """Streaming responses (EventStream) are never cached.

    The middleware check at ``middleware.py:59`` requires
    ``isinstance(response, Response)`` — anything streaming returns a
    different response class and falls through.
    """

    async def test_event_stream_not_cached(self) -> None:
        app = _app()
        _wire_cache(app)
        counter = {"calls": 0}

        async def _gen():
            yield "first"

        @app.route("/events", referenced=True)
        def events():
            counter["calls"] += 1
            return EventStream(_gen())

        async with TestClient(app) as client:
            await client.get("/events")
            await client.get("/events")

        # SSE responses always re-execute the handler.
        assert counter["calls"] == 2


# ---------------------------------------------------------------------------
# 4.6 — TTL expiry
# ---------------------------------------------------------------------------


class TestTTLExpiry:
    """After the configured TTL passes, the next GET re-executes the handler.

    Uses ``MemoryCacheBackend`` whose TTL is enforced via ``time.monotonic``
    in ``backends/memory.py:31``. A short ``ttl=1`` plus ``asyncio.sleep(1.2)``
    keeps the test under 2s while exercising the real TTL path (no time mock).
    """

    @pytest.mark.timeout(10)
    async def test_handler_reruns_after_ttl_expires(self) -> None:
        app = _app()
        _wire_cache(app, ttl=1)
        counter = {"calls": 0}

        @app.route("/short-cache")
        def short_cache():
            counter["calls"] += 1
            return f"call {counter['calls']}"

        async with TestClient(app) as client:
            await client.get("/short-cache")
            # Within TTL — second hit served from cache.
            await client.get("/short-cache")
            assert counter["calls"] == 1

            # Past TTL — handler runs again.
            await asyncio.sleep(1.2)
            await client.get("/short-cache")

        assert counter["calls"] == 2


# ---------------------------------------------------------------------------
# 4.7 — Backend get() exception → request still served, WARNING logged
# ---------------------------------------------------------------------------


class _BoomBackend:
    """Cache backend whose ``get()`` always raises — simulates a Redis outage."""

    async def get(self, key: str) -> bytes | None:
        raise RuntimeError("boom — backend unavailable")

    async def set(self, key: str, value: bytes, ttl: int = 0) -> None:
        # set() is reached after get() returns None; raising here would mask
        # the get() path under test. Make it a no-op so the test is focused.
        return None

    async def delete(self, key: str) -> None:
        return None

    async def clear(self) -> None:
        return None


class TestBackendExceptionLogged:
    """A failing backend must NOT crash the request — middleware logs and falls through.

    The middleware wraps ``backend.get`` in ``try/except Exception`` at
    ``middleware.py:42`` and emits a WARNING. The user gets their response;
    a Redis outage degrades caching, not the site.
    """

    async def test_get_exception_serves_handler_response_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        app = _app()
        _wire_cache(app, backend=_BoomBackend())

        @app.route("/")
        def index():
            return "<p>still served</p>"

        with caplog.at_level("WARNING", logger="chirp.cache"):
            async with TestClient(app) as client:
                response = await client.get("/")

        assert response.status == 200
        assert "still served" in response.text
        # Exactly one warning from chirp.cache; message references the cache key.
        warnings = [
            r for r in caplog.records if r.name == "chirp.cache" and r.levelname == "WARNING"
        ]
        assert len(warnings) == 1, (
            f"Expected one chirp.cache WARNING, got: "
            f"{[(r.name, r.levelname, r.getMessage()) for r in caplog.records]}"
        )
        assert "Cache get error" in warnings[0].getMessage()
