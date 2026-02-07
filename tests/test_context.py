"""Tests for chirp.context — request-scoped ContextVar and g namespace."""

import pytest

from chirp.app import App
from chirp.context import _RequestGlobals, g, get_request, request_var
from chirp.http.request import Request
from chirp.testing import TestClient


class TestRequestVar:
    def test_get_request_raises_outside_context(self) -> None:
        """get_request raises LookupError when no request is active."""
        with pytest.raises(LookupError):
            get_request()

    def test_set_and_get_request(self) -> None:
        """request_var can be set and retrieved."""
        # Create a minimal scope for Request.from_asgi
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "http_version": "1.1",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request.from_asgi(scope, receive)
        token = request_var.set(request)
        try:
            assert get_request() is request
            assert get_request().path == "/test"
        finally:
            request_var.reset(token)


class TestRequestGlobals:
    def test_set_and_get_attribute(self) -> None:
        ns = _RequestGlobals()
        ns.user = "alice"
        assert ns.user == "alice"

    def test_missing_attribute_raises(self) -> None:
        ns = _RequestGlobals()
        with pytest.raises(AttributeError, match="has no attribute 'missing'"):
            _ = ns.missing

    def test_delete_attribute(self) -> None:
        ns = _RequestGlobals()
        ns.foo = "bar"
        del ns.foo
        with pytest.raises(AttributeError, match="has no attribute 'foo'"):
            _ = ns.foo

    def test_delete_missing_raises(self) -> None:
        ns = _RequestGlobals()
        with pytest.raises(AttributeError, match="has no attribute 'nope'"):
            del ns.nope

    def test_contains(self) -> None:
        ns = _RequestGlobals()
        ns.x = 1
        assert "x" in ns
        assert "y" not in ns

    def test_get_with_default(self) -> None:
        ns = _RequestGlobals()
        assert ns.get("missing", 42) == 42
        ns.present = "yes"
        assert ns.get("present", "no") == "yes"

    def test_repr(self) -> None:
        ns = _RequestGlobals()
        ns.a = 1
        r = repr(ns)
        assert "a" in r
        assert "1" in r


class TestContextInRequestPipeline:
    """Integration tests: context var is set during request handling."""

    async def test_request_var_available_in_handler(self) -> None:
        app = App()

        @app.route("/ctx")
        def handler():
            req = get_request()
            return f"path={req.path}"

        async with TestClient(app) as client:
            response = await client.get("/ctx")
            assert response.status == 200
            assert response.text == "path=/ctx"

    async def test_g_namespace_in_middleware_and_handler(self) -> None:
        app = App()

        async def set_user(request: Request, next):
            g.user = "alice"
            return await next(request)

        app.add_middleware(set_user)

        @app.route("/whoami")
        def whoami():
            return f"user={g.user}"

        async with TestClient(app) as client:
            response = await client.get("/whoami")
            assert response.status == 200
            assert response.text == "user=alice"

    async def test_g_is_isolated_per_request(self) -> None:
        """Each request gets its own g namespace."""
        app = App()
        call_count = 0

        async def counting_mw(request: Request, next):
            nonlocal call_count
            call_count += 1
            g.count = call_count
            return await next(request)

        app.add_middleware(counting_mw)

        @app.route("/count")
        def count():
            return f"count={g.count}"

        async with TestClient(app) as client:
            r1 = await client.get("/count")
            r2 = await client.get("/count")
            assert r1.text == "count=1"
            assert r2.text == "count=2"

    async def test_request_var_reset_after_error(self) -> None:
        """request_var should be reset even when a handler raises."""
        app = App()

        @app.route("/boom")
        def boom():
            msg = "handler error"
            raise RuntimeError(msg)

        @app.route("/ok")
        def ok():
            return "fine"

        async with TestClient(app) as client:
            # First request raises — context should still be cleaned up
            r1 = await client.get("/boom")
            assert r1.status == 500

            # Second request should work normally
            r2 = await client.get("/ok")
            assert r2.status == 200
            assert r2.text == "fine"

    async def test_g_not_leaked_between_requests(self) -> None:
        """g attributes from one request should not leak to the next."""
        app = App()

        async def set_if_first(request: Request, next):
            if request.path == "/first":
                g.secret = "leaked"
            return await next(request)

        app.add_middleware(set_if_first)

        @app.route("/first")
        def first():
            return f"secret={g.secret}"

        @app.route("/second")
        def second():
            return f"has_secret={'secret' in g}"

        async with TestClient(app) as client:
            r1 = await client.get("/first")
            assert r1.text == "secret=leaked"

            r2 = await client.get("/second")
            assert r2.text == "has_secret=False"
