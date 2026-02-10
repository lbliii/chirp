"""Tests for chirp.http.request — frozen Request with async body access."""

import json

import pytest

from chirp.http.request import Request


def _make_scope(**overrides: object) -> dict[str, object]:
    """Build a minimal valid ASGI HTTP scope."""
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


def _make_receive(*bodies: bytes):
    """Create an ASGI receive callable that yields bodies."""
    messages = []
    for i, body in enumerate(bodies):
        is_last = i == len(bodies) - 1
        messages.append({"type": "http.request", "body": body, "more_body": not is_last})
    if not messages:
        messages.append({"type": "http.request", "body": b"", "more_body": False})
    it = iter(messages)

    async def receive():
        return next(it)

    return receive


class TestRequestFromASGI:
    def test_basic_fields(self) -> None:
        scope = _make_scope(method="POST", path="/users")
        req = Request.from_asgi(scope, _make_receive())

        assert req.method == "POST"
        assert req.path == "/users"
        assert req.http_version == "1.1"
        assert req.server == ("localhost", 8000)
        assert req.client == ("127.0.0.1", 54321)

    def test_path_params(self) -> None:
        scope = _make_scope(path="/users/42")
        req = Request.from_asgi(scope, _make_receive(), path_params={"id": "42"})

        assert req.path_params == {"id": "42"}

    def test_path_params_default_empty(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.path_params == {}

    def test_headers_parsed(self) -> None:
        scope = _make_scope(
            headers=[(b"content-type", b"application/json"), (b"accept", b"*/*")]
        )
        req = Request.from_asgi(scope, _make_receive())

        assert req.headers["content-type"] == "application/json"
        assert req.headers["accept"] == "*/*"

    def test_query_params_parsed(self) -> None:
        scope = _make_scope(query_string=b"q=hello&page=2")
        req = Request.from_asgi(scope, _make_receive())

        assert req.query["q"] == "hello"
        assert req.query["page"] == "2"

    def test_missing_server_and_client(self) -> None:
        scope = _make_scope()
        del scope["server"]
        del scope["client"]
        req = Request.from_asgi(scope, _make_receive())

        assert req.server is None
        assert req.client is None


class TestRequestCookies:
    def test_cookies_parsed_at_creation(self) -> None:
        scope = _make_scope(
            headers=[(b"cookie", b"session=abc123; theme=dark")]
        )
        req = Request.from_asgi(scope, _make_receive())

        assert req.cookies == {"session": "abc123", "theme": "dark"}

    def test_no_cookie_header(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.cookies == {}

    def test_cookies_is_same_object_on_repeated_access(self) -> None:
        scope = _make_scope(headers=[(b"cookie", b"a=1")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.cookies is req.cookies  # Same dict, not re-parsed


class TestRequestProperties:
    def test_is_fragment_true(self) -> None:
        scope = _make_scope(headers=[(b"hx-request", b"true")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.is_fragment is True

    def test_is_fragment_false(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.is_fragment is False

    def test_is_boosted_true(self) -> None:
        scope = _make_scope(headers=[(b"hx-boosted", b"true")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.is_boosted is True

    def test_is_boosted_false(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.is_boosted is False

    def test_htmx_target(self) -> None:
        scope = _make_scope(headers=[(b"hx-target", b"#results")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.htmx_target == "#results"

    def test_htmx_trigger(self) -> None:
        scope = _make_scope(headers=[(b"hx-trigger", b"search-input")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.htmx_trigger == "search-input"

    def test_htmx_trigger_name(self) -> None:
        scope = _make_scope(headers=[(b"hx-trigger-name", b"search-field")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.htmx_trigger_name == "search-field"

    def test_htmx_trigger_name_missing(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.htmx_trigger_name is None

    def test_content_type(self) -> None:
        scope = _make_scope(headers=[(b"content-type", b"application/json")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.content_type == "application/json"

    def test_content_length(self) -> None:
        scope = _make_scope(headers=[(b"content-length", b"42")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.content_length == 42

    def test_content_length_missing(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.content_length is None

    def test_content_length_invalid(self) -> None:
        scope = _make_scope(headers=[(b"content-length", b"abc")])
        req = Request.from_asgi(scope, _make_receive())

        assert req.content_length is None

    def test_url_without_query(self) -> None:
        scope = _make_scope(path="/users")
        req = Request.from_asgi(scope, _make_receive())

        assert req.url == "/users"

    def test_url_with_query(self) -> None:
        scope = _make_scope(path="/search", query_string=b"q=hello")
        req = Request.from_asgi(scope, _make_receive())

        assert req.url == "/search?q=hello"


class TestRequestBody:
    async def test_body(self) -> None:
        scope = _make_scope()
        req = Request.from_asgi(scope, _make_receive(b"hello world"))

        assert await req.body() == b"hello world"

    async def test_body_chunked(self) -> None:
        scope = _make_scope()
        req = Request.from_asgi(scope, _make_receive(b"hello ", b"world"))

        assert await req.body() == b"hello world"

    async def test_body_empty(self) -> None:
        scope = _make_scope()
        req = Request.from_asgi(scope, _make_receive())

        assert await req.body() == b""

    async def test_text(self) -> None:
        scope = _make_scope()
        req = Request.from_asgi(scope, _make_receive(b"hello"))

        assert await req.text() == "hello"

    async def test_json(self) -> None:
        scope = _make_scope()
        data = json.dumps({"key": "value"}).encode()
        req = Request.from_asgi(scope, _make_receive(data))

        result = await req.json()
        assert result == {"key": "value"}

    async def test_stream(self) -> None:
        scope = _make_scope()
        req = Request.from_asgi(scope, _make_receive(b"chunk1", b"chunk2"))

        chunks = [chunk async for chunk in req.stream()]
        assert chunks == [b"chunk1", b"chunk2"]


class TestRequestFrozen:
    def test_cannot_mutate(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())

        with pytest.raises(AttributeError):
            req.method = "POST"  # type: ignore[misc]
