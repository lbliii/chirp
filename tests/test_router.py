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

    def test_rejects_unknown_converter(self) -> None:
        with pytest.raises(ConfigurationError, match="Unknown path parameter converter 'uuid'"):
            parse_path("/users/{id:uuid}")

    def test_rejects_empty_param_name(self) -> None:
        with pytest.raises(ConfigurationError, match="cannot be empty"):
            parse_path("/users/{}")

    def test_rejects_malformed_param_segment(self) -> None:
        with pytest.raises(ConfigurationError, match="Malformed path parameter segment"):
            parse_path("/users/{id")

    def test_rejects_path_converter_before_final_segment(self) -> None:
        with pytest.raises(ConfigurationError, match="must be the final segment"):
            parse_path("/files/{filepath:path}/edit")

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

    def test_rejects_hyphenated_param(self) -> None:
        """Path parameters must be valid Python identifiers."""
        with pytest.raises(ConfigurationError) as exc_info:
            parse_path("/products/{product-id}")
        msg = str(exc_info.value)
        assert "product-id" in msg
        assert "product_id" in msg  # suggests the fix

    def test_rejects_param_starting_with_digit(self) -> None:
        """Params starting with digits are not valid identifiers."""
        with pytest.raises(ConfigurationError):
            parse_path("/items/{2nd_item}")

    def test_accepts_underscore_param(self) -> None:
        """Underscored params are valid identifiers."""
        segments = parse_path("/products/{product_id}")
        assert segments[1].param_name == "product_id"

    def test_rejects_python_keyword_param(self) -> None:
        """Python keywords like 'class' or 'return' are rejected."""
        with pytest.raises(ConfigurationError) as exc_info:
            parse_path("/items/{class}")
        msg = str(exc_info.value)
        assert "keyword" in msg
        assert "class" in msg

    def test_rejects_python_keyword_for(self) -> None:
        """The keyword 'for' is also rejected."""
        with pytest.raises(ConfigurationError):
            parse_path("/items/{for}")


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

    def test_typed_param_edges_do_not_shadow_string_param(self) -> None:
        r = Router()
        r.add(_route("/items/{id:int}"))
        r.add(_route("/items/{slug}"))
        r.compile()

        int_match = r.match("GET", "/items/42")
        slug_match = r.match("GET", "/items/readme")

        assert int_match.route.path == "/items/{id:int}"
        assert int_match.path_params == {"id": "42"}
        assert slug_match.route.path == "/items/{slug}"
        assert slug_match.path_params == {"slug": "readme"}

    def test_param_edges_keep_route_specific_param_names(self) -> None:
        r = Router()
        r.add(_route("/files/{bucket}/objects"))
        r.add(_route("/files/{key}/metadata"))
        r.compile()

        objects = r.match("GET", "/files/media/objects")
        metadata = r.match("GET", "/files/readme/metadata")

        assert objects.path_params == {"bucket": "media"}
        assert metadata.path_params == {"key": "readme"}

    def test_more_specific_param_converter_wins_independent_of_registration_order(self) -> None:
        r = Router()
        r.add(_route("/items/{slug}"))
        r.add(_route("/items/{id:int}"))
        r.compile()

        match = r.match("GET", "/items/42")

        assert match.route.path == "/items/{id:int}"
        assert match.path_params == {"id": "42"}

    def test_duplicate_param_shape_rejected(self) -> None:
        r = Router()
        r.add(_route("/users/{id}"))

        with pytest.raises(ConfigurationError, match="Duplicate route shape"):
            r.add(_route("/users/{name}"))


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
        assert "POST" in err.detail
        assert "/users" in err.detail
        assert "Allowed methods: GET" in err.detail
        allow_headers = dict(err.headers)
        assert "GET" in allow_headers["Allow"]

    @pytest.mark.issue(554)
    def test_head_falls_back_to_get_route(self) -> None:
        r = Router()
        get_route = _route("/users/{id}", frozenset({"GET"}))
        r.add(get_route)
        r.compile()

        match = r.match("HEAD", "/users/42")

        assert match.route is get_route
        assert match.path_params == {"id": "42"}

    @pytest.mark.issue(554)
    def test_explicit_head_route_takes_precedence(self) -> None:
        r = Router()
        get_route = _route("/users", frozenset({"GET"}))
        head_route = _route("/users", frozenset({"HEAD"}))
        r.add(get_route)
        r.add(head_route)
        r.compile()

        assert r.match("GET", "/users").route is get_route
        assert r.match("HEAD", "/users").route is head_route

    @pytest.mark.issue(554)
    def test_get_implies_head_in_allow_header(self) -> None:
        r = Router()
        r.add(_route("/users", frozenset({"GET"})))
        r.add(_route("/users", frozenset({"POST"})))
        r.compile()

        with pytest.raises(MethodNotAllowed) as exc_info:
            r.match("DELETE", "/users")

        assert dict(exc_info.value.headers)["Allow"] == "GET, HEAD, POST"

    @pytest.mark.issue(554)
    def test_head_does_not_fall_back_to_unrelated_method(self) -> None:
        r = Router()
        r.add(_route("/users", frozenset({"POST"})))
        r.compile()

        with pytest.raises(MethodNotAllowed) as exc_info:
            r.match("HEAD", "/users")

        assert dict(exc_info.value.headers)["Allow"] == "POST"

    @pytest.mark.issue(554)
    def test_head_fallback_works_for_catch_all_route(self) -> None:
        r = Router()
        get_route = _route("/files/{path:path}", frozenset({"GET"}))
        r.add(get_route)
        r.compile()

        match = r.match("HEAD", "/files/docs/index.html")

        assert match.route is get_route
        assert match.path_params == {"path": "docs/index.html"}


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
        with pytest.raises(ConfigurationError, match=r"<param>.*\{param\}"):
            r.add(_route("/share/<slug>"))
