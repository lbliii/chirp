"""Tests for fragment-aware error handling.

When htmx sends a fragment request and an error occurs, the response
should be a minimal HTML snippet instead of a full page.
"""


from chirp.app import App
from chirp.config import AppConfig
from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.testing import (
    TestClient,
    assert_fragment_contains,
    assert_is_error_fragment,
)


class TestDefaultFragmentErrors:
    """Default error responses for fragment requests."""

    async def test_404_fragment_returns_snippet(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.fragment("/nonexistent")
            assert_is_error_fragment(response, status=404)
            assert_fragment_contains(response, "No route matches")

    async def test_404_normal_returns_plain_text(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/nonexistent")
            assert response.status == 404
            assert "chirp-error" not in response.text

    async def test_405_fragment_returns_snippet(self) -> None:
        app = App()

        @app.route("/items", methods=["GET"])
        def items():
            return "items"

        async with TestClient(app) as client:
            response = await client.fragment("/items", method="POST")
            assert_is_error_fragment(response, status=405)

    async def test_500_fragment_returns_snippet(self) -> None:
        app = App()

        @app.route("/boom")
        def boom():
            msg = "test error"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.fragment("/boom")
            assert_is_error_fragment(response, status=500)
            assert_fragment_contains(response, "Internal Server Error")

    async def test_500_normal_returns_plain_text(self) -> None:
        app = App()

        @app.route("/boom")
        def boom():
            msg = "test error"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.get("/boom")
            assert response.status == 500
            assert response.text == "Internal Server Error"


class TestCustomErrorHandlersWithRequest:
    """Custom error handlers receive request and exception."""

    async def test_error_handler_receives_request(self) -> None:
        app = App()

        @app.error(404)
        def not_found(request: Request):
            if request.is_fragment:
                return '<div id="error">Not found (fragment)</div>'
            return "Page not found"

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            full = await client.get("/nonexistent")
            assert full.text == "Page not found"

            frag = await client.fragment("/nonexistent")
            assert frag.text == '<div id="error">Not found (fragment)</div>'

    async def test_error_handler_receives_exception(self) -> None:
        app = App()

        @app.error(404)
        def not_found(request: Request, exc: HTTPError):
            return f"detail={exc.detail}"

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/missing")
            assert response.status == 404
            assert "detail=" in response.text
            assert "No route matches" in response.text

    async def test_zero_arg_error_handler_still_works(self) -> None:
        """Backward compatibility: error handlers with no args still work."""
        app = App()

        @app.error(404)
        def not_found():
            return "custom 404"

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/missing")
            assert response.status == 404
            assert response.text == "custom 404"

    async def test_500_error_handler_with_exception(self) -> None:
        app = App()

        @app.error(500)
        def server_error(request: Request, exc: Exception):
            return Response(body=f"Error: {exc}", status=500)

        @app.route("/fail")
        def fail():
            msg = "something broke"
            raise ValueError(msg)

        async with TestClient(app) as client:
            response = await client.get("/fail")
            assert response.status == 500
            assert "something broke" in response.text


class TestAsyncErrorHandlers:
    """Async error handlers must be awaited."""

    async def test_async_error_handler(self) -> None:
        app = App()

        @app.error(404)
        async def not_found(request: Request):
            return "async 404"

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.get("/missing")
            assert response.status == 404
            assert response.text == "async 404"

    async def test_async_500_handler(self) -> None:
        app = App()

        @app.error(500)
        async def server_error(request: Request, exc: Exception):
            return Response(body=f"async error: {exc}", status=500)

        @app.route("/boom")
        def boom():
            msg = "kaboom"
            raise ValueError(msg)

        async with TestClient(app) as client:
            response = await client.get("/boom")
            assert response.status == 500
            assert "kaboom" in response.text

    async def test_async_error_handler_with_fragment(self) -> None:
        app = App()

        @app.error(404)
        async def not_found(request: Request):
            if request.is_fragment:
                return '<span class="err">gone</span>'
            return "not found"

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            frag = await client.fragment("/missing")
            assert frag.status == 404
            assert frag.text == '<span class="err">gone</span>'


class TestCustomHTTPErrorSubclass:
    """Custom HTTPError subclasses with fragment detection."""

    async def test_custom_http_error_fragment(self) -> None:
        app = App()

        @app.route("/forbidden")
        def forbidden():
            raise HTTPError(status=403, detail="Access denied")

        async with TestClient(app) as client:
            frag = await client.fragment("/forbidden")
            assert_is_error_fragment(frag, status=403)
            assert_fragment_contains(frag, "Access denied")

            full = await client.get("/forbidden")
            assert full.status == 403
            assert 'class="chirp-error"' not in full.text


class TestDebugModeFragmentErrors:
    """Debug mode with fragment requests."""

    async def test_debug_500_fragment_includes_traceback_in_div(self) -> None:
        app = App(config=AppConfig(debug=True))

        @app.route("/boom")
        def boom():
            msg = "debug error"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.fragment("/boom")
            assert_is_error_fragment(response, status=500)
            assert_fragment_contains(response, "debug error")
            # Rich debug page renders source context (not bare <pre>)
            assert_fragment_contains(response, "RuntimeError")

    async def test_debug_500_normal_includes_traceback(self) -> None:
        app = App(config=AppConfig(debug=True))

        @app.route("/boom")
        def boom():
            msg = "debug error"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.get("/boom")
            assert response.status == 500
            assert "debug error" in response.text
            assert "RuntimeError" in response.text
            # Full page uses error-page wrapper, not chirp-error
            assert 'class="error-page"' in response.text


class TestHtmxErrorHeaders:
    """Fragment error responses include htmx retargeting headers."""

    async def test_404_fragment_has_htmx_headers(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.fragment("/nonexistent")
            from chirp.testing import hx_headers

            hx = hx_headers(response)
            assert hx.get("HX-Retarget") == "#chirp-error"
            assert hx.get("HX-Reswap") == "innerHTML"
            assert hx.get("HX-Trigger") == "chirpError"

    async def test_500_fragment_has_htmx_headers(self) -> None:
        app = App()

        @app.route("/boom")
        def boom():
            msg = "kaboom"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.fragment("/boom")
            from chirp.testing import hx_headers

            hx = hx_headers(response)
            assert hx.get("HX-Retarget") == "#chirp-error"
            assert hx.get("HX-Reswap") == "innerHTML"
            assert hx.get("HX-Trigger") == "chirpError"

    async def test_non_fragment_has_no_htmx_headers(self) -> None:
        app = App()

        @app.route("/boom")
        def boom():
            msg = "kaboom"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.get("/boom")
            from chirp.testing import hx_headers

            hx = hx_headers(response)
            assert "HX-Retarget" not in hx
            assert "HX-Reswap" not in hx
            assert "HX-Trigger" not in hx

    async def test_debug_500_fragment_has_htmx_headers(self) -> None:
        app = App(config=AppConfig(debug=True))

        @app.route("/boom")
        def boom():
            msg = "debug kaboom"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.fragment("/boom")
            from chirp.testing import hx_headers

            hx = hx_headers(response)
            assert hx.get("HX-Retarget") == "#chirp-error"
            assert hx.get("HX-Reswap") == "innerHTML"

    async def test_custom_http_error_fragment_has_htmx_headers(self) -> None:
        app = App()

        @app.route("/forbidden")
        def forbidden():
            raise HTTPError(status=403, detail="Access denied")

        async with TestClient(app) as client:
            response = await client.fragment("/forbidden")
            from chirp.testing import hx_headers

            hx = hx_headers(response)
            assert hx.get("HX-Retarget") == "#chirp-error"


class TestErrorLogging:
    """Error handlers emit log records."""

    async def test_500_logs_exception(self, caplog) -> None:
        app = App()

        @app.route("/boom")
        def boom():
            msg = "log test"
            raise RuntimeError(msg)

        with caplog.at_level("ERROR", logger="chirp.server"):
            async with TestClient(app) as client:
                await client.get("/boom")

        assert any("500 GET /boom" in r.message for r in caplog.records)
        # logger.exception() captures the traceback
        assert any(r.exc_info for r in caplog.records)

    async def test_404_logs_at_debug_level(self, caplog) -> None:
        app = App()

        @app.route("/")
        def index():
            return "home"

        with caplog.at_level("DEBUG", logger="chirp.server"):
            async with TestClient(app) as client:
                await client.get("/missing")

        assert any("404" in r.message and "/missing" in r.message for r in caplog.records)
