"""RFC 10008 QUERY discovery and response-semantics proof (#526)."""

from pathlib import Path

import httpx
import pytest

from chirp import App, FileResponse, Redirect, Request, Response
from chirp.server.sender import send_file_response
from chirp.testing import TestClient

_LAST_MODIFIED = "Sun, 06 Nov 1994 08:49:37 GMT"
_ETAG = 'W/"search-v1"'


def _header(response: Response, name: str) -> str | None:
    target = name.lower()
    return next((value for key, value in response.headers if key.lower() == target), None)


def _headers(response: Response, name: str) -> list[str]:
    target = name.lower()
    return [value for key, value in response.headers if key.lower() == target]


def _search_app() -> App:
    app = App()

    @app.route(
        "/search",
        methods=["GET", "QUERY"],
        query_media_types=(
            "application/json",
            'application/sql;charset="UTF-8"',
        ),
    )
    def search(request: Request) -> Response:
        return (
            Response(f"result:{request.method}")
            .with_header("ETag", _ETAG)
            .with_header("Last-Modified", _LAST_MODIFIED)
            .with_header("Location", "/searches/q_7f83b165")
            .with_header("Content-Location", "/results/r_54a59b9f")
            .with_header("Link", "</schema/search>; rel=describedby")
            .with_header("Link", "</search/help>; rel=help")
        )

    return app


@pytest.mark.issue(526)
async def test_query_path_synthesizes_options_discovery() -> None:
    app = _search_app()
    async with TestClient(app) as client:
        response = await client.request("OPTIONS", "/search?tenant=west")

    assert response.status == 204
    assert response.body == b""
    assert _header(response, "Allow") == "GET, HEAD, OPTIONS, QUERY"
    assert _header(response, "Accept-Query") == ("application/json, application/sql;charset=utf-8")


async def test_explicit_options_route_wins_over_generated_discovery() -> None:
    app = _search_app()

    @app.route("/search", methods=["OPTIONS"])
    def options() -> Response:
        return Response("custom options").with_header("X-Options-Owner", "application")

    async with TestClient(app) as client:
        response = await client.request("OPTIONS", "/search")

    assert response.status == 200
    assert response.text == "custom options"
    assert _header(response, "X-Options-Owner") == "application"


async def test_405_includes_query_and_structured_discovery_headers() -> None:
    app = _search_app()
    async with TestClient(app) as client:
        response = await client.post("/search", body=b"not a mutation")

    assert response.status == 405
    assert _header(response, "Allow") == "GET, HEAD, OPTIONS, QUERY"
    assert _header(response, "Accept-Query") == ("application/json, application/sql;charset=utf-8")


async def test_custom_405_page_preserves_allow_and_accept_query() -> None:
    app = _search_app()

    @app.error(405)
    def method_not_allowed() -> Response:
        return Response("custom 405")

    async with TestClient(app) as client:
        response = await client.post("/search")

    assert response.status == 405
    assert response.text == "custom 405"
    assert _header(response, "Allow") == "GET, HEAD, OPTIONS, QUERY"
    assert _header(response, "Accept-Query") is not None


async def test_non_query_405_does_not_gain_query_discovery() -> None:
    app = App()

    @app.route("/ordinary")
    def ordinary() -> str:
        return "ok"

    async with TestClient(app) as client:
        response = await client.post("/ordinary")

    assert response.status == 405
    assert _header(response, "Allow") == "GET, HEAD"
    assert _header(response, "Accept-Query") is None


async def test_equivalent_resource_headers_are_opaque_and_multi_value_safe() -> None:
    app = _search_app()
    sensitive_query = b'{"account":"private@example.test"}'
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers={"Content-Type": "application/json"},
            body=sensitive_query,
        )

    assert response.status == 200
    location = _header(response, "Location")
    content_location = _header(response, "Content-Location")
    assert location == "/searches/q_7f83b165"
    assert content_location == "/results/r_54a59b9f"
    assert sensitive_query.decode() not in location
    assert sensitive_query.decode() not in content_location
    assert _headers(response, "Link") == [
        "</schema/search>; rel=describedby",
        "</search/help>; rel=help",
    ]


@pytest.mark.parametrize("method", ["GET", "QUERY"])
@pytest.mark.parametrize("if_none_match", [_ETAG, '"search-v1"', "*"])
async def test_get_and_query_share_weak_etag_conditional_semantics(
    method: str, if_none_match: str
) -> None:
    app = _search_app()
    headers = {"If-None-Match": if_none_match}
    if method == "QUERY":
        headers["Content-Type"] = "application/json"
    async with TestClient(app) as client:
        response = await client.request(method, "/search", headers=headers, body=b"{}")

    assert response.status == 304
    assert response.body == b""
    assert _header(response, "ETag") == _ETAG
    assert _header(response, "Last-Modified") == _LAST_MODIFIED


async def test_if_none_match_takes_precedence_over_if_modified_since() -> None:
    app = _search_app()
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers={
                "Content-Type": "application/json",
                "If-None-Match": '"different"',
                "If-Modified-Since": _LAST_MODIFIED,
            },
            body=b"{}",
        )

    assert response.status == 200
    assert response.text == "result:QUERY"


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({"If-Match": "*"}, 200),
        ({"If-Match": _ETAG}, 412),
        ({"If-Match": '"different"'}, 412),
        ({"If-Unmodified-Since": _LAST_MODIFIED}, 200),
        ({"If-Unmodified-Since": "Sun, 06 Nov 1993 08:49:37 GMT"}, 412),
        (
            {
                "If-Match": "*",
                "If-Unmodified-Since": "Sun, 06 Nov 1993 08:49:37 GMT",
            },
            200,
        ),
    ],
)
async def test_query_state_changing_preconditions_use_rfc_order(
    headers: dict[str, str], expected_status: int
) -> None:
    app = _search_app()
    request_headers = {"Content-Type": "application/json", **headers}
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers=request_headers,
            body=b"{}",
        )

    assert response.status == expected_status
    if expected_status == 412:
        assert response.body == b""


@pytest.mark.parametrize(
    ("if_modified_since", "expected_status"),
    [
        (_LAST_MODIFIED, 304),
        ("Sun, 06 Nov 2094 08:49:37 GMT", 304),
        ("Sun, 06 Nov 1993 08:49:37 GMT", 200),
        ("not-a-date", 200),
    ],
)
async def test_query_if_modified_since(if_modified_since: str, expected_status: int) -> None:
    app = _search_app()
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            "/search",
            headers={
                "Content-Type": "application/json",
                "If-Modified-Since": if_modified_since,
            },
            body=b"{}",
        )

    assert response.status == expected_status


@pytest.mark.parametrize(
    "status",
    [301, 302, 307, 308, 303],
)
async def test_chirp_preserves_query_redirect_status_and_location(status: int) -> None:
    app = App()

    @app.route(
        "/redirect/{status:int}",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    def redirect(status: int) -> Redirect:
        return Redirect("/target", status=status)

    async with TestClient(app) as client:
        response = await client.request(
            "QUERY",
            f"/redirect/{status}",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )

    assert response.status == status
    assert _header(response, "Location") == "/target"


async def test_303_hands_an_http_client_off_to_get() -> None:
    app = App()

    @app.route(
        "/redirect",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    def redirect() -> Redirect:
        return Redirect("/target", status=303)

    @app.route("/target")
    def target(request: Request) -> str:
        return request.method

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
    ) as client:
        response = await client.request(
            "QUERY",
            "/redirect",
            headers={"Content-Type": "application/json"},
            content=b"{}",
        )

    assert response.status_code == 200
    assert response.text == "GET"
    assert [item.status_code for item in response.history] == [303]


async def test_query_file_response_retains_conditional_and_range_semantics(
    tmp_path: Path,
) -> None:
    asset = tmp_path / "result.txt"
    asset.write_bytes(b"query-result")

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    request = Request.from_asgi(
        {
            "type": "http",
            "method": "QUERY",
            "path": "/result-file",
            "headers": [(b"range", b"bytes=0-4")],
        },
        receive,
    )
    messages: list[dict] = []

    async def send(message: dict) -> None:
        messages.append(message)

    await send_file_response(FileResponse(asset), send, request=request)

    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = {name.decode("latin-1"): value.decode("latin-1") for name, value in start["headers"]}
    body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    assert start["status"] == 206
    assert body == b"query"
    assert headers["content-range"] == "bytes 0-4/12"
    assert headers["accept-ranges"] == "bytes"
    assert "etag" in headers
