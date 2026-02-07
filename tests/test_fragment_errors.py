"""Tests for fragment-aware error handling.

When htmx sends a fragment request and an error occurs, the response
should be a minimal HTML snippet instead of a full page.
"""


from chirp.app import App
from chirp.config import AppConfig
from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.testing import TestClient


class TestDefaultFragmentErrors:
    """Default error responses for fragment requests."""

    async def test_404_fragment_returns_snippet(self) -> None:
        app = App()

        @app.route("/")
        def index():
            return "home"

        async with TestClient(app) as client:
            response = await client.fragment("/nonexistent")
            assert response.status == 404
            assert 'class="chirp-error"' in response.text
            assert 'data-status="404"' in response.text
            assert "No route matches" in response.text

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
            assert response.status == 405
            assert 'class="chirp-error"' in response.text

    async def test_500_fragment_returns_snippet(self) -> None:
        app = App()

        @app.route("/boom")
        def boom():
            msg = "test error"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.fragment("/boom")
            assert response.status == 500
            assert 'class="chirp-error"' in response.text
            assert "Internal Server Error" in response.text

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
            assert response.status == 500
            assert 'class="chirp-error"' in response.text
            assert "debug error" in response.text
            assert "<pre>" in response.text

    async def test_debug_500_normal_includes_traceback(self) -> None:
        app = App(config=AppConfig(debug=True))

        @app.route("/boom")
        def boom():
            msg = "debug error"
            raise RuntimeError(msg)

        async with TestClient(app) as client:
            response = await client.get("/boom")
            assert response.status == 500
            assert "<pre>" in response.text
            assert "debug error" in response.text
            # Normal (non-fragment) should NOT have the chirp-error wrapper
            assert 'class="chirp-error"' not in response.text
