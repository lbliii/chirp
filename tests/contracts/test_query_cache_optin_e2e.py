"""End-to-end opt-in QUERY response-cache contracts (#531)."""

from __future__ import annotations

import asyncio

import pytest

from chirp import App, AppConfig, Response, Stream
from chirp.cache.backends.memory import MemoryCacheBackend
from chirp.cache.key import query_cache_key
from chirp.cache.middleware import CacheMiddleware
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(531)

_HEADERS = {"Content-Type": "application/json", "Accept": "text/html"}


def _app(*, enabled: bool = True, ttl: int = 300):
    backend = MemoryCacheBackend()
    app = App(AppConfig(skip_contract_checks=True))

    async def key(request):
        return await query_cache_key(request, vary_headers=("x-tenant",))

    app.add_middleware(
        CacheMiddleware(
            backend,
            ttl=ttl,
            query_key_func=key if enabled else None,
        )
    )
    return app, backend


async def test_query_cache_is_default_off_and_explicitly_opted_in() -> None:
    disabled, _ = _app(enabled=False)
    enabled, _ = _app(enabled=True)
    disabled_calls = 0
    enabled_calls = 0

    @disabled.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    async def disabled_search(request):
        nonlocal disabled_calls
        disabled_calls += 1
        return f"disabled:{await request.text()}:{disabled_calls}"

    @enabled.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    async def enabled_search(request):
        nonlocal enabled_calls
        enabled_calls += 1
        return f"enabled:{await request.text()}:{enabled_calls}"

    async with TestClient(disabled) as client:
        await client.request("QUERY", "/search", headers=_HEADERS, body=b"same")
        await client.request("QUERY", "/search", headers=_HEADERS, body=b"same")
    async with TestClient(enabled) as client:
        first = await client.request("QUERY", "/search", headers=_HEADERS, body=b"same")
        second = await client.request("QUERY", "/search", headers=_HEADERS, body=b"same")

    assert disabled_calls == 2
    assert enabled_calls == 1
    assert first.text == second.text == "enabled:same:1"


async def test_query_cache_separates_body_media_accept_tenant_and_htmx_target() -> None:
    app, _ = _app()
    calls = 0

    @app.route("/search", methods=["QUERY"], query_media_types=("application/*",))
    async def search(request):
        nonlocal calls
        calls += 1
        return Response(
            f"{request.content_type}|{request.headers.get('accept')}|"
            f"{request.headers.get('x-tenant')}|{request.htmx_target_id}|"
            f"{(await request.body()).decode()}|{calls}"
        )

    variants = [
        ({**_HEADERS, "X-Tenant": "a"}, b"one"),
        ({**_HEADERS, "X-Tenant": "a"}, b"two"),
        (
            {"Content-Type": "application/problem+json", "Accept": "text/html", "X-Tenant": "a"},
            b"one",
        ),
        ({"Content-Type": "application/json", "Accept": "text/*", "X-Tenant": "a"}, b"one"),
        ({**_HEADERS, "X-Tenant": "b"}, b"one"),
        ({**_HEADERS, "X-Tenant": "a", "HX-Request": "true", "HX-Target": "results"}, b"one"),
        ({**_HEADERS, "X-Tenant": "a", "HX-Request": "true", "HX-Target": "sidebar"}, b"one"),
    ]
    async with TestClient(app) as client:
        first = [
            await client.request("QUERY", "/search", headers=headers, body=body)
            for headers, body in variants
        ]
        second = [
            await client.request("QUERY", "/search", headers=headers, body=body)
            for headers, body in variants
        ]

    assert calls == len(variants)
    assert [item.text for item in first] == [item.text for item in second]


@pytest.mark.parametrize("private_header", ["Cookie", "Authorization"])
async def test_private_query_requests_bypass_cache(private_header: str) -> None:
    app, backend = _app()
    calls = 0

    @app.route("/private", methods=["QUERY"], query_media_types=("application/json",))
    def private():
        nonlocal calls
        calls += 1
        return f"private:{calls}"

    headers = {**_HEADERS, private_header: "secret"}
    async with TestClient(app) as client:
        await client.request("QUERY", "/private", headers=headers, body=b"{}")
        await client.request("QUERY", "/private", headers=headers, body=b"{}")

    assert calls == 2
    assert backend._store == {}


async def test_combined_private_cookie_values_cannot_bypass_privacy_guard() -> None:
    app, backend = _app()
    calls = 0

    @app.route("/private", methods=["QUERY"], query_media_types=("application/json",))
    def private():
        nonlocal calls
        calls += 1
        return "private"

    headers = {
        **_HEADERS,
        "Cookie": "empty=; session=secret",
    }
    async with TestClient(app) as client:
        await client.request("QUERY", "/private", headers=headers, body=b"{}")
        await client.request("QUERY", "/private", headers=headers, body=b"{}")

    assert calls == 2
    assert backend._store == {}


async def test_set_cookie_and_streaming_query_responses_are_uncached(tmp_path) -> None:
    (tmp_path / "stream.html").write_text("<p>{{ value }}</p>")
    app, backend = _app()
    cookie_calls = 0
    stream_calls = 0

    @app.route("/cookie", methods=["QUERY"], query_media_types=("application/json",))
    def cookie():
        nonlocal cookie_calls
        cookie_calls += 1
        return Response(f"cookie:{cookie_calls}").with_cookie("session", "value")

    def stream():
        nonlocal stream_calls
        stream_calls += 1
        return Stream("stream.html", value=stream_calls)

    # Stream needs a template environment, so use a dedicated app with the same cache policy.
    stream_backend = MemoryCacheBackend()
    stream_app = App(AppConfig(skip_contract_checks=True, template_dir=tmp_path))
    stream_app.add_middleware(CacheMiddleware(stream_backend, query_key_func=query_cache_key))
    stream_app.route("/stream", methods=["QUERY"], query_media_types=("application/json",))(stream)

    async with TestClient(app) as client:
        await client.request("QUERY", "/cookie", headers=_HEADERS, body=b"{}")
        await client.request("QUERY", "/cookie", headers=_HEADERS, body=b"{}")
    async with TestClient(stream_app) as client:
        await client.request("QUERY", "/stream", headers=_HEADERS, body=b"{}")
        await client.request("QUERY", "/stream", headers=_HEADERS, body=b"{}")

    assert cookie_calls == 2
    assert stream_calls == 2
    assert backend._store == {}
    assert stream_backend._store == {}


async def test_cached_query_hit_reapplies_validators_and_preserves_render_intent() -> None:
    app, _ = _app()
    calls = 0

    @app.route("/validated", methods=["QUERY"], query_media_types=("application/json",))
    def validated():
        nonlocal calls
        calls += 1
        return (
            Response("validated", render_intent="fragment")
            .with_header("ETag", 'W/"query-v1"')
            .with_header("Content-Location", "/results/opaque")
        )

    async with TestClient(app) as client:
        first = await client.request("QUERY", "/validated", headers=_HEADERS, body=b"{}")
        cached = await client.request("QUERY", "/validated", headers=_HEADERS, body=b"{}")
        conditional = await client.request(
            "QUERY",
            "/validated",
            headers={**_HEADERS, "If-None-Match": '"query-v1"'},
            body=b"{}",
        )

    assert calls == 1
    assert first.header("X-Chirp-Render-Intent") == "fragment"
    assert cached.header("X-Chirp-Render-Intent") == "fragment"
    assert conditional.status == 304
    assert conditional.body == b""
    assert conditional.header("ETag") == 'W/"query-v1"'
    assert conditional.header("Content-Location") == "/results/opaque"


class _FailingBackend:
    async def get(self, key: str) -> bytes | None:
        raise RuntimeError("unavailable")

    async def set(self, key: str, value: bytes, ttl: int = 0) -> None:
        raise RuntimeError("unavailable")


async def test_query_backend_failure_logs_and_fails_open(caplog) -> None:
    app = App(AppConfig(skip_contract_checks=True))
    app.add_middleware(CacheMiddleware(_FailingBackend(), query_key_func=query_cache_key))

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    def search():
        return "served"

    with caplog.at_level("WARNING", logger="chirp.cache"):
        async with TestClient(app) as client:
            response = await client.request("QUERY", "/search", headers=_HEADERS, body=b"{}")

    assert response.status == 200
    assert response.text == "served"
    assert any("Cache get error" in record.getMessage() for record in caplog.records)
    assert any("Cache set error" in record.getMessage() for record in caplog.records)


async def test_concurrent_query_variants_do_not_cross_contaminate() -> None:
    app, _ = _app()

    @app.route("/search", methods=["QUERY"], query_media_types=("application/json",))
    async def search(request):
        await asyncio.sleep(0)
        return await request.text()

    bodies = [f'{{"term":{index}}}'.encode() for index in range(40)]
    async with TestClient(app) as client:
        responses = await asyncio.gather(
            *(client.request("QUERY", "/search", headers=_HEADERS, body=body) for body in bodies)
        )
        hits = await asyncio.gather(
            *(client.request("QUERY", "/search", headers=_HEADERS, body=body) for body in bodies)
        )

    assert [response.body for response in responses] == bodies
    assert [response.body for response in hits] == bodies
