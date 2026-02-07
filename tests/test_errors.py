"""Tests for chirp.errors — exception hierarchy and error messages."""

import pytest

from chirp.errors import (
    ChirpError,
    ConfigurationError,
    HTTPError,
    MethodNotAllowed,
    NotFound,
)
from chirp.routing.route import Route
from chirp.routing.router import Router


class TestHierarchy:
    def test_http_error_is_chirp_error(self) -> None:
        assert issubclass(HTTPError, ChirpError)

    def test_not_found_is_http_error(self) -> None:
        assert issubclass(NotFound, HTTPError)

    def test_method_not_allowed_is_http_error(self) -> None:
        assert issubclass(MethodNotAllowed, HTTPError)

    def test_configuration_error_is_chirp_error(self) -> None:
        assert issubclass(ConfigurationError, ChirpError)


class TestHTTPError:
    def test_status_and_detail(self) -> None:
        err = HTTPError(status=400, detail="Bad request body")
        assert err.status == 400
        assert err.detail == "Bad request body"

    def test_str_with_detail(self) -> None:
        err = HTTPError(status=400, detail="Bad request body")
        assert str(err) == "400: Bad request body"

    def test_str_without_detail(self) -> None:
        err = HTTPError(status=500)
        assert str(err) == "500"

    def test_frozen(self) -> None:
        err = HTTPError(status=400)
        with pytest.raises(AttributeError):
            err.status = 500  # type: ignore[misc]

    def test_default_empty_headers(self) -> None:
        err = HTTPError(status=400)
        assert err.headers == ()


class TestNotFound:
    def test_defaults(self) -> None:
        err = NotFound()
        assert err.status == 404
        assert err.detail == "Not Found"

    def test_custom_detail(self) -> None:
        err = NotFound("Page /foo not found")
        assert err.status == 404
        assert err.detail == "Page /foo not found"

    def test_catchable_as_http_error(self) -> None:
        with pytest.raises(HTTPError):
            raise NotFound()


class TestMethodNotAllowed:
    def test_defaults(self) -> None:
        err = MethodNotAllowed(frozenset({"GET", "POST"}))
        assert err.status == 405
        # Detail includes allowed methods
        assert "GET" in err.detail
        assert "POST" in err.detail
        assert "Method not allowed" in err.detail

    def test_custom_detail(self) -> None:
        err = MethodNotAllowed(frozenset({"GET"}), detail="Custom message")
        assert err.detail == "Custom message"

    def test_allow_header(self) -> None:
        err = MethodNotAllowed(frozenset({"GET", "POST", "DELETE"}))
        allow_headers = dict(err.headers)
        assert "Allow" in allow_headers
        # Sorted alphabetically
        assert allow_headers["Allow"] == "DELETE, GET, POST"

    def test_detail_matches_allow_header(self) -> None:
        err = MethodNotAllowed(frozenset({"GET", "PUT"}))
        allow_headers = dict(err.headers)
        # Allowed methods appear in both the detail and the Allow header
        assert "GET" in err.detail
        assert "PUT" in err.detail
        assert allow_headers["Allow"] == "GET, PUT"

    def test_catchable_as_http_error(self) -> None:
        with pytest.raises(HTTPError):
            raise MethodNotAllowed(frozenset({"GET"}))


class TestRouterErrorMessages:
    """Router raises NotFound and MethodNotAllowed with informative details."""

    def _make_router(self) -> Router:
        """Build a simple router for testing error messages."""

        def handler():
            return "ok"

        router = Router()
        router.add(Route(path="/items", handler=handler, methods=frozenset({"GET"}), name=None))
        router.add(
            Route(path="/items", handler=handler, methods=frozenset({"POST"}), name=None)
        )
        router.compile()
        return router

    def test_not_found_includes_method_and_path(self) -> None:
        router = self._make_router()
        with pytest.raises(NotFound, match="GET") as exc_info:
            router.match("GET", "/nonexistent")
        assert "/nonexistent" in exc_info.value.detail

    def test_method_not_allowed_includes_allowed_methods(self) -> None:
        router = self._make_router()
        with pytest.raises(MethodNotAllowed) as exc_info:
            router.match("DELETE", "/items")
        assert "GET" in exc_info.value.detail
        assert "POST" in exc_info.value.detail


class TestErrorExports:
    """Error types are importable from the top-level chirp package."""

    def test_import_chirp_error(self) -> None:
        import chirp

        assert chirp.ChirpError is ChirpError

    def test_import_http_error(self) -> None:
        import chirp

        assert chirp.HTTPError is HTTPError

    def test_import_not_found(self) -> None:
        import chirp

        assert chirp.NotFound is NotFound

    def test_import_method_not_allowed(self) -> None:
        import chirp

        assert chirp.MethodNotAllowed is MethodNotAllowed

    def test_import_configuration_error(self) -> None:
        import chirp

        assert chirp.ConfigurationError is ConfigurationError
