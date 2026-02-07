"""Tests for chirp._internal.asgi — typed ASGI definitions."""

import pytest

from chirp._internal.asgi import HTTPScope


def _make_scope(**overrides: object) -> dict[str, object]:
    """Build a minimal valid ASGI HTTP scope dict."""
    base: dict[str, object] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 54321),
    }
    base.update(overrides)
    return base


class TestHTTPScope:
    def test_from_scope_basic(self) -> None:
        scope = _make_scope(method="POST", path="/users/42")
        parsed = HTTPScope.from_scope(scope)

        assert parsed.type == "http"
        assert parsed.method == "POST"
        assert parsed.path == "/users/42"
        assert parsed.http_version == "1.1"
        assert parsed.server == ("localhost", 8000)
        assert parsed.client == ("127.0.0.1", 54321)

    def test_from_scope_headers_become_tuple(self) -> None:
        raw_headers = [(b"content-type", b"text/html"), (b"accept", b"*/*")]
        scope = _make_scope(headers=raw_headers)
        parsed = HTTPScope.from_scope(scope)

        assert isinstance(parsed.headers, tuple)
        assert len(parsed.headers) == 2
        assert parsed.headers[0] == (b"content-type", b"text/html")

    def test_from_scope_defaults_for_missing_keys(self) -> None:
        minimal: dict[str, object] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "GET",
            "path": "/",
        }
        parsed = HTTPScope.from_scope(minimal)

        assert parsed.http_version == "1.1"
        assert parsed.raw_path == b""
        assert parsed.query_string == b""
        assert parsed.root_path == ""
        assert parsed.headers == ()
        assert parsed.server is None
        assert parsed.client is None

    def test_frozen(self) -> None:
        scope = _make_scope()
        parsed = HTTPScope.from_scope(scope)

        with pytest.raises(AttributeError):
            parsed.method = "POST"  # type: ignore[misc]

    def test_query_string_preserved(self) -> None:
        scope = _make_scope(query_string=b"q=hello&page=2")
        parsed = HTTPScope.from_scope(scope)

        assert parsed.query_string == b"q=hello&page=2"
