"""Tests for chirp.routing.router — compiled trie-based router."""

import pytest

from chirp.errors import ConfigurationError, MethodNotAllowed, NotFound
from chirp.routing.route import Route
from chirp.routing.router import Router, parse_path


def _handler() -> str:
    return "ok"


def _route(path: str, methods: frozenset[str] | None = None) -> Route:
    return Route(path=path, handler=_handler, methods=methods or frozenset({"GET"}))


class TestParsePath:
    def test_static(self) -> None:
        segments = parse_path("/users")
        assert len(segments) == 1
        assert segments[0].value == "users"
        assert segments[0].is_param is False

    def test_multi_static(self) -> None:
        segments = parse_path("/api/v2/users")
        assert len(segments) == 3
        assert [s.value for s in segments] == ["api", "v2", "users"]

    def test_param(self) -> None:
        segments = parse_path("/users/{id}")
        assert len(segments) == 2
        assert segments[1].is_param is True
        assert segments[1].param_name == "id"
        assert segments[1].param_type == "str"

    def test_typed_param(self) -> None:
        segments = parse_path("/users/{id:int}")
        assert segments[1].param_type == "int"

    def test_path_param(self) -> None:
        segments = parse_path("/files/{filepath:path}")
        assert segments[1].param_type == "path"
        assert segments[1].param_name == "filepath"

    def test_root(self) -> None:
        segments = parse_path("/")
        assert segments == []

    def test_rejects_flask_style_param(self) -> None:
        """Chirp expects {param}, not <param>."""
        with pytest.raises(ConfigurationError) as exc_info:
            parse_path("/share/<slug>")
        assert "<param>" in str(exc_info.value)
        assert "{param}" in str(exc_info.value)
        assert "/share/<slug>" in str(exc_info.value)


class TestRouterStaticRoutes:
    def test_root(self) -> None:
        r = Router()
        r.add(_route("/"))
        r.compile()

        match = r.match("GET", "/")
        assert match.path_params == {}

    def test_simple_path(self) -> None:
        r = Router()
        r.add(_route("/users"))
        r.compile()

        match = r.match("GET", "/users")
        assert match.route.path == "/users"

    def test_nested_path(self) -> None:
        r = Router()
        r.add(_route("/api/v2/users"))
        r.compile()

        match = r.match("GET", "/api/v2/users")
        assert match.route.path == "/api/v2/users"

    def test_multiple_routes(self) -> None:
        r = Router()
        r.add(_route("/users"))
        r.add(_route("/posts"))
        r.compile()

        assert r.match("GET", "/users").route.path == "/users"
        assert r.match("GET", "/posts").route.path == "/posts"

    def test_trailing_slash_ignored(self) -> None:
        r = Router()
        r.add(_route("/users"))
        r.compile()

        match = r.match("GET", "/users/")
        assert match.route.path == "/users"


class TestRouterParams:
    def test_string_param(self) -> None:
        r = Router()
        r.add(_route("/users/{name}"))
        r.compile()

        match = r.match("GET", "/users/alice")
        assert match.path_params == {"name": "alice"}

    def test_int_param(self) -> None:
        r = Router()
        r.add(_route("/users/{id:int}"))
        r.compile()

        match = r.match("GET", "/users/42")
        assert match.path_params == {"id": "42"}

    def test_int_param_rejects_non_digit(self) -> None:
        r = Router()
        r.add(_route("/users/{id:int}"))
        r.compile()

        with pytest.raises(NotFound):
            r.match("GET", "/users/alice")

    def test_float_param(self) -> None:
        r = Router()
        r.add(_route("/price/{amount:float}"))
        r.compile()

        match = r.match("GET", "/price/9.99")
        assert match.path_params == {"amount": "9.99"}

    def test_multiple_params(self) -> None:
        r = Router()
        r.add(_route("/users/{user_id:int}/posts/{post_id:int}"))
        r.compile()

        match = r.match("GET", "/users/1/posts/42")
        assert match.path_params == {"user_id": "1", "post_id": "42"}

    def test_path_param(self) -> None:
        r = Router()
        r.add(_route("/files/{filepath:path}"))
        r.compile()

        match = r.match("GET", "/files/docs/api/v2/index.html")
        assert match.path_params == {"filepath": "docs/api/v2/index.html"}

    def test_static_preferred_over_param(self) -> None:
        """Static segments match before parameter segments."""
        r = Router()
        r.add(_route("/users/me"))
        r.add(_route("/users/{id}"))
        r.compile()

        match = r.match("GET", "/users/me")
        assert match.route.path == "/users/me"

        match2 = r.match("GET", "/users/42")
        assert match2.route.path == "/users/{id}"


class TestRouterMethods:
    def test_method_filtering(self) -> None:
        r = Router()
        r.add(_route("/users", frozenset({"GET"})))
        r.add(_route("/users", frozenset({"POST"})))
        r.compile()

        get_match = r.match("GET", "/users")
        assert "GET" in get_match.route.methods

        post_match = r.match("POST", "/users")
        assert "POST" in post_match.route.methods

    def test_method_not_allowed(self) -> None:
        r = Router()
        r.add(_route("/users", frozenset({"GET"})))
        r.compile()

        with pytest.raises(MethodNotAllowed) as exc_info:
            r.match("POST", "/users")

        err = exc_info.value
        assert err.status == 405
        allow_headers = dict(err.headers)
        assert "GET" in allow_headers["Allow"]


class TestRouterErrors:
    def test_not_found(self) -> None:
        r = Router()
        r.add(_route("/users"))
        r.compile()

        with pytest.raises(NotFound) as exc_info:
            r.match("GET", "/nonexistent")

        assert exc_info.value.status == 404

    def test_add_after_compile_raises(self) -> None:
        r = Router()
        r.compile()

        with pytest.raises(RuntimeError, match="Cannot add routes after compilation"):
            r.add(_route("/users"))

    def test_add_rejects_flask_style_param(self) -> None:
        r = Router()
        with pytest.raises(ConfigurationError, match="<param>.*\\{param\\}"):
            r.add(_route("/share/<slug>"))
