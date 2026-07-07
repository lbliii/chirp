"""RFC 10008 QUERY registration and failure-semantics proof (#525)."""

import inspect

import pytest
from pounce.sync_protocol import RawRequest

from chirp import App, AppConfig, ConfigurationError, HTTPError, Request, Response
from chirp.http.query_media import (
    normalize_query_media_types,
    response_content_type_acceptable,
    serialize_accept_query,
)
from chirp.server.sync_handler import handle_sync
from chirp.testing import TestClient


def _header(response: Response, name: str) -> str | None:
    target = name.lower()
    return next((value for key, value in response.headers if key.lower() == target), None)


def test_route_signature_exposes_only_the_accepted_query_keyword() -> None:
    parameter = inspect.signature(App.route).parameters["query_media_types"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_query_route_requires_declared_media_types() -> None:
    app = App()

    @app.route("/search", methods=["QUERY"])
    def search() -> str:
        return "ok"

    with pytest.raises(
        ConfigurationError,
        match=r"QUERY route '/search'.*query_media_types",
    ):
        app.freeze()


def test_query_metadata_is_rejected_on_non_query_route() -> None:
    app = App()

    @app.route("/search", query_media_types=("application/json",))
    def search() -> str:
        return "ok"

    with pytest.raises(ConfigurationError, match=r"'/search'.*does not include 'QUERY'"):
        app.freeze()


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        (("application",), "expected type/subtype"),
        (("*/json",), "invalid wildcard"),
        (("application/json", "APPLICATION/JSON"), "duplicate"),
        (("application/json;broken",), "invalid media-type parameter"),
        (["application/json"], "must be a tuple"),
    ],
)
def test_invalid_query_media_declarations_fail_at_freeze(
    declaration: tuple[str, ...], message: str
) -> None:
    app = App()

    @app.route(  # type: ignore[arg-type]
        "/search",
        methods=["QUERY"],
        query_media_types=declaration,
    )
    def search() -> str:
        return "ok"

    with pytest.raises(ConfigurationError, match=message):
        app.freeze()


def test_query_media_types_are_normalized_sorted_and_frozen() -> None:
    app = App()

    @app.route(
        "/search",
        methods=["query"],
        query_media_types=(
            'text/plain; charset="UTF-8"',
            "APPLICATION/JSON",
        ),
    )
    def search() -> str:
        return "ok"

    app.freeze()
    route = next(route for route in app._router.routes if route.path == "/search")
    assert route.methods == frozenset({"QUERY"})
    assert route.query_media_types == (
        "application/json",
        "text/plain;charset=utf-8",
    )


def test_mount_app_preserves_query_route_metadata() -> None:
    parent = App()
    child = App()

    @child.route(
        "/search",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    def search() -> str:
        return "ok"

    parent.mount_app("/api", child)
    parent.freeze()
    route = next(route for route in parent._router.routes if route.path == "/api/search")
    assert route.query_media_types == ("application/json",)


def test_accept_query_uses_structured_field_serialization() -> None:
    normalized = normalize_query_media_types(
        (
            "application/sql; charset=UTF-8",
            '1example/query; profile="two words"',
        )
    )
    assert serialize_accept_query(normalized) == (
        '"1example/query";profile="two words", application/sql;charset=utf-8'
    )


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        (None, True),
        ("*/*", True),
        ("text/*", True),
        ("application/json, text/html;q=0.5", True),
        ("text/html;q=0, */*;q=1", False),
        ("application/json", False),
        ("not-a-media-type", False),
    ],
)
def test_response_accept_matching_honors_specificity(accept: str | None, expected: bool) -> None:
    assert response_content_type_acceptable("text/html; charset=utf-8", accept) is expected


def _query_app(*, max_body_size: int = 1024) -> tuple[App, list[bytes]]:
    app = App(AppConfig(max_request_body_size=max_body_size))
    calls: list[bytes] = []

    @app.route(
        "/search",
        methods=["QUERY"],
        query_media_types=(
            "application/json",
            "application/x-www-form-urlencoded",
        ),
    )
    async def search(request: Request) -> Response:
        body = await request.body()
        calls.append(body)
        if body == b"malformed":
            raise HTTPError(400, "Malformed JSON for QUERY route '/search'.")
        if body == b"unknown-field":
            raise HTTPError(422, "Unknown search field for QUERY route '/search'.")
        return Response(f"{request.url}:{body.decode()}")

    return app, calls


@pytest.mark.issue(525)
@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({}, 400),
        ({"Content-Type": "application"}, 400),
        ({"Content-Type": "text/plain"}, 415),
        ({"Content-Type": "application/json, text/plain"}, 400),
    ],
)
async def test_query_rejects_bad_content_type_before_handler(
    headers: dict[str, str], expected_status: int
) -> None:
    app, calls = _query_app()
    async with TestClient(app) as client:
        response = await client.request("QUERY", "/search", headers=headers, body=b"{}")

    assert response.status == expected_status
    assert calls == []
    assert _header(response, "Accept-Query") == (
        "application/json, application/x-www-form-urlencoded"
    )
    assert "/search" in response.text


async def test_query_accepts_declared_content_and_preserves_uri_query() -> None:
    app, calls = _query_app()
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search?tenant=west",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "text/html",
            },
            body=b"{}",
        )

    assert response.status == 200
    assert response.text == "/search?tenant=west:{}"
    assert calls == [b"{}"]


async def test_query_metadata_does_not_change_other_methods_on_the_same_route() -> None:
    app = App()

    @app.route(
        "/search",
        methods=["GET", "QUERY"],
        query_media_types=("application/json",),
    )
    def search() -> str:
        return "ok"

    async with TestClient(app) as client:
        response = await client.get("/search")

    assert response.status == 200
    assert response.text == "ok"
    assert _header(response, "Accept-Query") is None


async def test_query_returns_406_after_negotiation_when_accept_is_unsatisfied() -> None:
    app, calls = _query_app()
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body=b"{}",
        )

    assert response.status == 406
    assert calls == [b"{}"]
    assert "text/html; charset=utf-8" in response.text
    assert _header(response, "Accept-Query") is not None


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [(b"malformed", 400), (b"unknown-field", 422)],
)
async def test_query_handler_maps_syntax_and_semantic_failures(
    body: bytes, expected_status: int
) -> None:
    app, _ = _query_app()
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers={"Content-Type": "application/json"},
            body=body,
        )

    assert response.status == expected_status
    assert _header(response, "Accept-Query") is not None


async def test_query_body_limit_matches_other_body_bearing_methods() -> None:
    app, calls = _query_app(max_body_size=4)
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers={"Content-Type": "application/json"},
            body=b"12345",
        )

    assert response.status == 413
    assert calls == []
    assert "4 bytes" in response.text
    assert _header(response, "Accept-Query") is not None


async def test_custom_error_page_keeps_query_protocol_headers() -> None:
    app, _ = _query_app()

    @app.error(415)
    def unsupported() -> Response:
        return Response("custom unsupported")

    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers={"Content-Type": "text/plain"},
            body=b"query",
        )

    assert response.status == 415
    assert response.text == "custom unsupported"
    assert _header(response, "Accept-Query") is not None


def test_fused_sync_path_always_falls_through_for_query() -> None:
    app, _ = _query_app()
    app.freeze()
    raw = RawRequest(
        method=b"QUERY",
        path=b"/search",
        query_string=b"",
        headers=((b"content-type", b"application/json"),),
        body=b"{}",
        client=("127.0.0.1", 12345),
        server=("127.0.0.1", 8000),
        http_version=b"1.1",
    )

    assert handle_sync(raw, app._router, middleware=(), providers=None) is None


async def test_sync_query_handler_runs_through_asgi_with_the_same_contract() -> None:
    app = App()
    calls: list[str] = []

    @app.route(
        "/sync-search",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    def search() -> str:
        calls.append("called")
        return "sync result"

    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/sync-search",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )

    assert response.status == 200
    assert response.text == "sync result"
    assert calls == ["called"]
