"""End-to-end HTTP QUERY proof across Chirp's HTML render surfaces (#529)."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import pytest

from chirp import (
    OOB,
    App,
    AppConfig,
    Fragment,
    Page,
    Redirect,
    Stream,
    Suspense,
    ValidationError,
)
from chirp.errors import HTTPError
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(529)

_TEMPLATES = Path(__file__).parent / "templates" / "query_rendering"
_QUERY_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}
_HTMX_QUERY_HEADERS = {**_QUERY_HEADERS, "HX-Request": "true", "HX-Target": "query-target"}


def _decode_trace(value: str | None) -> dict[str, object]:
    assert value is not None
    return json.loads(base64.b64decode(value).decode("utf-8"))


def _app() -> App:
    app = App(
        AppConfig(
            debug=True,
            skip_contract_checks=True,
            template_dir=_TEMPLATES,
        )
    )

    @app.route(
        "/query/page",
        methods=["QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    def page_query() -> Page:
        return Page(
            "page.html",
            "content",
            page_block_name="page_root",
            message="page-query-result",
            notice="ready",
        )

    @app.route(
        "/query/fragment",
        methods=["QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    async def fragment_query() -> Fragment:
        await asyncio.sleep(0)
        return Fragment("page.html", "content", message="fragment-query-result")

    @app.route(
        "/query/oob",
        methods=["QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    def oob_query() -> OOB:
        return OOB(
            Fragment("page.html", "content", message="oob-query-result"),
            Fragment("page.html", "notice", target="notice", notice="query-complete"),
        )

    @app.route(
        "/query/oob-missing",
        methods=["QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    def missing_oob_query() -> OOB:
        return OOB(
            Fragment("page.html", "content", message="must-not-swap"),
            Fragment("page.html", "missing", target="missing-region"),
        )

    @app.route(
        "/query/stream",
        methods=["QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    def stream_query() -> Stream:
        return Stream("stream.html", value="stream-query-result")

    @app.route(
        "/query/suspense",
        methods=["QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    async def suspense_query() -> Suspense:
        async def resolve_result() -> str:
            await asyncio.sleep(0)
            return "suspense-query-result"

        return Suspense("suspense.html", result=resolve_result())

    @app.route(
        "/query/validate",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    async def validate_query(request) -> Fragment | ValidationError:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPError(400, "Malformed JSON for QUERY route '/query/validate'.") from exc
        if payload.get("term") != "chirp":
            return ValidationError(
                "page.html",
                "content",
                retarget="#query-target",
                message="query-validation-error",
            )
        return Fragment("page.html", "content", message="query-validation-ok")

    @app.route(
        "/query/redirect",
        methods=["QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    def redirect_query() -> Redirect:
        return Redirect("/query/result", status=303)

    return app


async def test_query_page_uses_full_document_and_narrow_htmx_block() -> None:
    app = _app()
    async with TestClient(app) as client:
        full = await client.request(
            "QUERY", "/query/page", headers=_QUERY_HEADERS, body=b"term=chirp"
        )
        narrow = await client.request(
            "QUERY", "/query/page", headers=_HTMX_QUERY_HEADERS, body=b"term=chirp"
        )

    assert full.status == narrow.status == 200
    assert "<!doctype html>" in full.text.lower()
    assert "<html" in full.text.lower()
    assert "page-query-result" in full.text
    assert "<!doctype html>" not in narrow.text.lower()
    assert "<html" not in narrow.text.lower()
    assert "page-query-result" in narrow.text

    full_trace = _decode_trace(full.header("X-Chirp-Return-Trace"))
    narrow_trace = _decode_trace(narrow.header("X-Chirp-Return-Trace"))
    assert full_trace["method"] == narrow_trace["method"] == "QUERY"
    assert full_trace["request_content_type"] == "application/x-www-form-urlencoded"
    assert full_trace["render_intent"] == "full_page"
    assert full_trace["is_htmx"] is False
    assert narrow_trace["render_intent"] == "fragment"
    assert narrow_trace["block"] == "content"
    assert narrow_trace["is_htmx"] is True


async def test_query_fragment_and_oob_keep_named_block_contracts() -> None:
    app = _app()
    async with TestClient(app) as client:
        fragment = await client.request(
            "QUERY", "/query/fragment", headers=_HTMX_QUERY_HEADERS, body=b"term=chirp"
        )
        oob = await client.request(
            "QUERY", "/query/oob", headers=_HTMX_QUERY_HEADERS, body=b"term=chirp"
        )

    assert fragment.status == oob.status == 200
    assert "fragment-query-result" in fragment.text
    assert "<html" not in fragment.text.lower()
    assert "oob-query-result" in oob.text
    assert "query-complete" in oob.text
    assert 'id="notice" hx-swap-oob="true"' in oob.text
    assert _decode_trace(fragment.header("X-Chirp-Return-Trace"))["block"] == "content"
    assert _decode_trace(oob.header("X-Chirp-Return-Trace"))["return_type"] == "OOB"


async def test_query_missing_oob_block_fails_loud_without_empty_swap() -> None:
    app = _app()
    async with TestClient(app) as client:
        response = await client.request(
            "QUERY", "/query/oob-missing", headers=_HTMX_QUERY_HEADERS, body=b"term=chirp"
        )

    assert response.status == 500
    assert '<div id="missing-region" hx-swap-oob' not in response.text


async def test_query_stream_and_suspense_preserve_chunk_order() -> None:
    app = _app()
    async with TestClient(app) as client:
        stream = await client.request_chunks(
            "QUERY", "/query/stream", headers=_QUERY_HEADERS, body=b"term=chirp"
        )
        suspense = await client.request_chunks(
            "QUERY", "/query/suspense", headers=_HTMX_QUERY_HEADERS, body=b"term=chirp"
        )

    assert stream.status == suspense.status == 200
    assert stream.streaming is True
    assert "stream-start" in stream.text
    assert "stream-query-result" in stream.text
    assert "stream-end" in stream.text
    assert suspense.streaming is True
    assert suspense.index_of("query-pending") < suspense.index_of("suspense-query-result")
    assert 'hx-swap-oob="true"' in suspense.text

    stream_trace = _decode_trace(stream.header("X-Chirp-Return-Trace"))
    suspense_trace = _decode_trace(suspense.header("X-Chirp-Return-Trace"))
    assert stream_trace["method"] == suspense_trace["method"] == "QUERY"
    assert stream_trace["return_type"] == "Stream"
    assert stream_trace["streaming"] is True
    assert suspense_trace["return_type"] == "Suspense"
    assert suspense_trace["streaming"] is True


async def test_query_malformed_validation_and_redirect_responses_stay_typed() -> None:
    app = _app()
    async with TestClient(app) as client:
        malformed = await client.request(
            "QUERY",
            "/query/validate",
            headers={"Content-Type": "application/json"},
            body=b"{",
        )
        invalid = await client.request(
            "QUERY",
            "/query/validate",
            headers={"Content-Type": "application/json", "HX-Request": "true"},
            body=b'{"term":"wrong"}',
        )
        redirect = await client.request(
            "QUERY", "/query/redirect", headers=_QUERY_HEADERS, body=b"term=chirp"
        )

    assert malformed.status == 400
    assert "Malformed JSON" in malformed.text
    assert invalid.status == 422
    assert invalid.header("HX-Retarget") == "#query-target"
    assert "query-validation-error" in invalid.text
    invalid_trace = _decode_trace(invalid.header("X-Chirp-Return-Trace"))
    assert invalid_trace["return_type"] == "ValidationError"
    assert invalid_trace["method"] == "QUERY"
    assert invalid_trace["is_htmx"] is True
    assert redirect.status == 303
    assert redirect.header("Location") == "/query/result"
