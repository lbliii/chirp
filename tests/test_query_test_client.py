"""Public TestClient.query() ergonomics for RFC 10008 (#527)."""

import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from chirp import App, Request, Response
from chirp.testing import TestClient


def _query_app(seen: list[dict[str, Any]]) -> App:
    app = App()

    @app.route(
        "/search",
        methods=["QUERY"],
        query_media_types=(
            "application/json",
            "application/x-www-form-urlencoded",
            "text/plain",
        ),
    )
    async def search(request: Request) -> Response:
        seen.append(
            {
                "body": await request.body(),
                "content_type": request.headers.get("content-type"),
                "method": request.method,
                "query": request.query.get("cursor"),
            }
        )
        return Response("ok")

    return app


@pytest.mark.issue(527)
def test_query_exposes_the_approved_public_signature() -> None:
    parameters = inspect.signature(TestClient.query).parameters

    assert tuple(parameters) == ("self", "path", "headers", "body", "data", "json")
    for name in ("headers", "body", "data", "json"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters[name].default is None


@pytest.mark.issue(527)
async def test_query_preserves_raw_body_content_type_and_uri_query() -> None:
    seen: list[dict[str, Any]] = []
    async with TestClient(_query_app(seen)) as client:
        response = await client.query(
            "/search?cursor=next",
            body=b"exact raw body",
            headers={"Content-Type": "text/plain"},
        )

    assert response.status == 200
    assert seen == [
        {
            "body": b"exact raw body",
            "content_type": "text/plain",
            "method": "QUERY",
            "query": "next",
        }
    ]


@pytest.mark.issue(527)
async def test_query_encodes_form_data_with_repeated_values() -> None:
    seen: list[dict[str, Any]] = []
    data: Mapping[str, str | Sequence[str]] = {
        "tag": ["python", "hypermedia"],
        "term": "named blocks",
    }

    async with TestClient(_query_app(seen)) as client:
        response = await client.query("/search", data=data)

    assert response.status == 200
    assert seen[0]["body"] == b"tag=python&tag=hypermedia&term=named+blocks"
    assert seen[0]["content_type"] == "application/x-www-form-urlencoded"
    assert seen[0]["method"] == "QUERY"


@pytest.mark.issue(527)
async def test_query_encodes_json_body() -> None:
    seen: list[dict[str, Any]] = []
    payload = {"filters": ["active", "recent"], "limit": 0}

    async with TestClient(_query_app(seen)) as client:
        response = await client.query("/search", json=payload)

    assert response.status == 200
    assert json.loads(seen[0]["body"]) == payload
    assert seen[0]["content_type"] == "application/json"
    assert seen[0]["method"] == "QUERY"


@pytest.mark.issue(527)
async def test_query_explicit_header_overrides_inferred_content_type() -> None:
    seen: list[dict[str, Any]] = []

    async with TestClient(_query_app(seen)) as client:
        response = await client.query(
            "/search",
            data={"term": "chirp"},
            headers={"Content-Type": "text/plain"},
        )

    assert response.status == 200
    assert seen[0]["content_type"] == "text/plain"
    assert seen[0]["body"] == b"term=chirp"


@pytest.mark.issue(527)
async def test_query_mixed_case_header_overrides_inferred_json_content_type() -> None:
    seen: list[dict[str, Any]] = []

    async with TestClient(_query_app(seen)) as client:
        response = await client.query(
            "/search",
            json={"term": "chirp"},
            headers={"Content-Type": "text/plain"},
        )

    assert response.status == 200
    assert seen[0]["content_type"] == "text/plain"
    assert json.loads(seen[0]["body"]) == {"term": "chirp"}


@pytest.mark.issue(527)
async def test_query_raw_body_without_content_type_uses_protocol_error() -> None:
    seen: list[dict[str, Any]] = []

    async with TestClient(_query_app(seen)) as client:
        response = await client.query("/search", body=b"term=chirp")

    assert response.status == 400
    assert "Content-Type" in response.text
    assert seen == []


@pytest.mark.issue(527)
@pytest.mark.parametrize(
    ("body", "data", "json_body"),
    [
        (b"", {}, None),
        (b"", None, {}),
        (None, {}, {}),
        (b"raw", {"term": "chirp"}, {"term": "chirp"}),
    ],
)
async def test_query_rejects_multiple_body_sources(
    body: bytes | None,
    data: Mapping[str, str | Sequence[str]] | None,
    json_body: dict[str, object] | None,
) -> None:
    client = TestClient(App())

    with pytest.raises(
        TypeError,
        match=r"only one of 'body', 'data', or 'json'",
    ):
        await client.query("/search", body=body, data=data, json=json_body)
