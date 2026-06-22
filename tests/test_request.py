"""Tests for chirp.http.request — frozen Request with async body access."""

import json
from dataclasses import dataclass

import pytest

from chirp.http.request import HtmxDetails, Request, RequestUrlScope


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

    def test_request_id_generated_when_missing(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.request_id
        assert len(req.request_id) == 36  # UUID format

    def test_request_id_from_header(self) -> None:
        scope = _make_scope(headers=[(b"x-request-id", b"my-correlation-id")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.request_id == "my-correlation-id"

    def test_request_id_from_scope_extensions(self) -> None:
        """Pounce and other ASGI servers set scope['extensions']['request_id']."""
        scope = _make_scope(extensions={"request_id": "pounce-abc123"})
        req = Request.from_asgi(scope, _make_receive())
        assert req.request_id == "pounce-abc123"

    def test_request_id_scope_extensions_over_header(self) -> None:
        """Scope extensions take precedence over X-Request-ID header."""
        scope = _make_scope(
            headers=[(b"x-request-id", b"header-id")],
            extensions={"request_id": "scope-id"},
        )
        req = Request.from_asgi(scope, _make_receive())
        assert req.request_id == "scope-id"

    def test_headers_parsed(self) -> None:
        scope = _make_scope(headers=[(b"content-type", b"application/json"), (b"accept", b"*/*")])
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


class TestTrustedClientIP:
    def test_returns_client_ip_when_present(self) -> None:
        req = Request.from_asgi(_make_scope(client=("203.0.113.7", 443)), _make_receive())
        assert req.trusted_client_ip == "203.0.113.7"

    def test_returns_unknown_when_client_missing(self) -> None:
        scope = _make_scope()
        del scope["client"]
        req = Request.from_asgi(scope, _make_receive())
        assert req.trusted_client_ip == "unknown"

    def test_ignores_raw_x_forwarded_for(self) -> None:
        """Fail-closed: a spoofable X-Forwarded-For never overrides client[0]."""
        scope = _make_scope(
            client=("10.0.0.1", 443),
            headers=[(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")],
        )
        req = Request.from_asgi(scope, _make_receive())
        assert req.trusted_client_ip == "10.0.0.1"

    def test_never_raises(self) -> None:
        scope = _make_scope()
        del scope["client"]
        req = Request.from_asgi(scope, _make_receive())
        # Property access must not raise even with no client.
        assert isinstance(req.trusted_client_ip, str)


class TestRequestUrlScope:
    def test_normalizes_prefix(self) -> None:
        scope = RequestUrlScope("c/acme/")

        assert scope.prefix == "/c/acme"

    def test_rejects_non_path_prefix(self) -> None:
        with pytest.raises(ValueError, match="app-root path prefix"):
            RequestUrlScope("https://example.com/c/acme")

    def test_apply_scopes_app_root_urls(self) -> None:
        scope = RequestUrlScope("/c/acme")

        assert scope.apply("/boards/ic?page=2") == "/c/acme/boards/ic?page=2"
        assert scope.apply("/?page=2") == "/c/acme?page=2"

    def test_apply_leaves_non_app_root_urls_alone(self) -> None:
        scope = RequestUrlScope("/c/acme")

        assert scope.apply("boards/ic") == "boards/ic"
        assert scope.apply("#reply") == "#reply"
        assert scope.apply("//cdn.example/app.css") == "//cdn.example/app.css"
        assert scope.apply("https://example.com/boards/ic") == "https://example.com/boards/ic"

    def test_apply_does_not_double_scope(self) -> None:
        scope = RequestUrlScope("/c/acme")

        assert scope.apply("/c/acme/boards/ic") == "/c/acme/boards/ic"

    def test_request_scoped_url_uses_attached_scope(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive()).with_url_scope("/c/acme")

        assert req.scoped_url("/boards/ic") == "/c/acme/boards/ic"

    def test_request_url_for_requires_bound_resolver(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive()).with_url_scope("/c/acme")

        with pytest.raises(RuntimeError, match="app/server pipeline"):
            req.url_for("boards.detail")

    def test_request_url_for_applies_scope_to_bound_resolver(self) -> None:
        def resolver(name: str, /, **params: object) -> str:
            assert name == "boards.detail"
            return f"/boards/{params['board_id']}"

        req = Request.from_asgi(
            _make_scope(),
            _make_receive(),
            url_for=resolver,
        ).with_url_scope("/c/acme")

        assert req.url_for("boards.detail", board_id="ic") == "/c/acme/boards/ic"


class TestRequestCookies:
    def test_cookies_parsed_at_creation(self) -> None:
        scope = _make_scope(headers=[(b"cookie", b"session=abc123; theme=dark")])
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

        with pytest.warns(DeprecationWarning, match="request.is_fragment is ambiguous"):
            assert req.is_fragment is True

    def test_is_fragment_false(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        with pytest.warns(DeprecationWarning, match="request.is_fragment is ambiguous"):
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

    def test_htmx_target_id_hashed(self) -> None:
        scope = _make_scope(headers=[(b"hx-target", b"#results")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_target_id == "results"
        assert req.htmx.target_id == "results"

    def test_htmx_target_id_bare(self) -> None:
        scope = _make_scope(headers=[(b"hx-target", b"results")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_target_id == "results"

    def test_htmx_target_id_missing(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.htmx_target_id is None
        assert req.htmx.target_id is None

    def test_htmx_target_id_empty_hash(self) -> None:
        scope = _make_scope(headers=[(b"hx-target", b"#")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_target_id is None

    def test_htmx_target_id_double_hash(self) -> None:
        scope = _make_scope(headers=[(b"hx-target", b"##panel")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_target_id == "panel"

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

    def test_is_history_restore_true(self) -> None:
        scope = _make_scope(headers=[(b"hx-history-restore-request", b"true")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.is_history_restore is True

    def test_is_history_restore_false(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.is_history_restore is False

    # -- URI-AutoEncoded --

    def test_htmx_target_uri_autoencoded(self) -> None:
        scope = _make_scope(
            headers=[
                (b"hx-target", b"%23results%20panel"),
                (b"hx-target-uri-autoencoded", b"true"),
            ]
        )
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_target == "#results panel"

    def test_htmx_trigger_uri_autoencoded(self) -> None:
        scope = _make_scope(
            headers=[
                (b"hx-trigger", b"btn%20%23click"),
                (b"hx-trigger-uri-autoencoded", b"true"),
            ]
        )
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_trigger == "btn #click"

    def test_htmx_header_without_autoencoded_returns_raw(self) -> None:
        scope = _make_scope(headers=[(b"hx-trigger", b"btn%20%23click")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_trigger == "btn%20%23click"

    # -- HX-Current-URL --

    def test_htmx_current_url(self) -> None:
        scope = _make_scope(headers=[(b"hx-current-url", b"http://localhost:8000/dashboard")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_current_url == "http://localhost:8000/dashboard"

    def test_htmx_current_url_missing(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.htmx_current_url is None

    def test_htmx_current_url_abs_path_same_origin(self) -> None:
        scope = _make_scope(headers=[(b"hx-current-url", b"http://localhost:8000/dash?tab=users")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_current_url_abs_path == "/dash?tab=users"

    def test_htmx_current_url_abs_path_different_origin(self) -> None:
        scope = _make_scope(headers=[(b"hx-current-url", b"http://other:9000/page")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_current_url_abs_path == "http://other:9000/page"

    def test_htmx_current_url_abs_path_missing(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.htmx_current_url_abs_path is None

    def test_htmx_current_url_uri_autoencoded(self) -> None:
        scope = _make_scope(
            headers=[
                (b"hx-current-url", b"http://localhost:8000/search%3Fq%3Dhello"),
                (b"hx-current-url-uri-autoencoded", b"true"),
            ]
        )
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx_current_url == "http://localhost:8000/search?q=hello"

    # -- request.htmx namespace --

    def test_htmx_details_truthy(self) -> None:
        scope = _make_scope(headers=[(b"hx-request", b"true")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx
        assert isinstance(req.htmx, HtmxDetails)

    def test_htmx_details_falsy(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert not req.htmx

    def test_htmx_details_cached(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())
        assert req.htmx is req.htmx

    def test_htmx_details_target(self) -> None:
        scope = _make_scope(
            headers=[
                (b"hx-target", b"%23main"),
                (b"hx-target-uri-autoencoded", b"true"),
            ]
        )
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.target == "#main"

    def test_htmx_details_trigger(self) -> None:
        scope = _make_scope(headers=[(b"hx-trigger", b"btn")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.trigger == "btn"

    def test_htmx_details_trigger_name(self) -> None:
        scope = _make_scope(headers=[(b"hx-trigger-name", b"search")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.trigger_name == "search"

    def test_htmx_details_boosted(self) -> None:
        scope = _make_scope(headers=[(b"hx-boosted", b"true")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.boosted is True

    def test_htmx_details_history_restore(self) -> None:
        scope = _make_scope(headers=[(b"hx-history-restore-request", b"true")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.history_restore is True

    def test_htmx_details_current_url(self) -> None:
        scope = _make_scope(headers=[(b"hx-current-url", b"http://localhost:8000/page")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.current_url == "http://localhost:8000/page"

    def test_htmx_details_current_url_abs_path(self) -> None:
        scope = _make_scope(headers=[(b"hx-current-url", b"http://localhost:8000/page?q=1")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.current_url_abs_path == "/page?q=1"

    def test_htmx_details_prompt(self) -> None:
        scope = _make_scope(headers=[(b"hx-prompt", b"user input")])
        req = Request.from_asgi(scope, _make_receive())
        assert req.htmx.prompt == "user input"

    def test_htmx_details_caching(self) -> None:
        """Verify values are cached on second access."""
        scope = _make_scope(headers=[(b"hx-target", b"panel")])
        req = Request.from_asgi(scope, _make_receive())
        _ = req.htmx.target  # First access populates cache
        assert req.htmx.target == "panel"  # Second access hits cache

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


class TestRequestUser:
    """request.user mirrors current_user(): never raises, AnonymousUser default."""

    def test_user_anonymous_without_auth_middleware(self) -> None:
        from chirp.middleware.auth import AnonymousUser

        req = Request.from_asgi(_make_scope(), _make_receive())
        user = req.user

        assert isinstance(user, AnonymousUser)
        assert user.is_authenticated is False

    def test_user_matches_current_user(self) -> None:
        from chirp.middleware.auth import _user_var, current_user

        @dataclass(frozen=True, slots=True)
        class _FakeUser:
            id: str = "42"
            is_authenticated: bool = True

        fake = _FakeUser()
        token = _user_var.set(fake)
        try:
            req = Request.from_asgi(_make_scope(), _make_receive())
            assert req.user is fake
            assert req.user is current_user()
        finally:
            _user_var.reset(token)


class TestRequestSession:
    """request.session mirrors get_session(): fail-loud LookupError, same dict."""

    def test_session_raises_without_session_middleware(self) -> None:
        req = Request.from_asgi(_make_scope(), _make_receive())

        with pytest.raises(LookupError, match="No active session"):
            _ = req.session

    def test_session_returns_get_session_dict(self) -> None:
        from chirp.middleware.sessions import _session_var, get_session

        active: dict[str, object] = {"cart": ["x"]}
        token = _session_var.set(active)
        try:
            req = Request.from_asgi(_make_scope(), _make_receive())
            assert req.session is active
            assert req.session is get_session()
            # Ergonomic .get() works directly on request.session
            assert req.session.get("cart") == ["x"]
            assert req.session.get("missing") is None
        finally:
            _session_var.reset(token)
