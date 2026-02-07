"""Tests for chirp.errors — exception hierarchy."""

import pytest

from chirp.errors import (
    ChirpError,
    ConfigurationError,
    HTTPError,
    MethodNotAllowed,
    NotFound,
)


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
        assert err.detail == "Method Not Allowed"

    def test_allow_header(self) -> None:
        err = MethodNotAllowed(frozenset({"GET", "POST", "DELETE"}))
        allow_headers = dict(err.headers)
        assert "Allow" in allow_headers
        # Sorted alphabetically
        assert allow_headers["Allow"] == "DELETE, GET, POST"

    def test_catchable_as_http_error(self) -> None:
        with pytest.raises(HTTPError):
            raise MethodNotAllowed(frozenset({"GET"}))
