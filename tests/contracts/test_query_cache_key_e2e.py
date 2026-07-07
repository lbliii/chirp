"""HTTP lifecycle proof for the QUERY cache-key design (#530)."""

from __future__ import annotations

import pytest

from chirp import App, AppConfig, Response
from chirp.cache.backends.memory import MemoryCacheBackend
from chirp.cache.key import query_cache_key
from chirp.cache.middleware import CacheMiddleware
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(530)


async def test_query_key_buffers_once_for_handler_while_cache_stays_bypassed() -> None:
    backend = MemoryCacheBackend()
    app = App(AppConfig(skip_contract_checks=True))
    app.add_middleware(CacheMiddleware(backend))
    calls = 0

    @app.route(
        "/search",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    async def search(request) -> Response:
        nonlocal calls
        calls += 1
        key = await query_cache_key(request, vary_headers=("x-search-version",))
        body = await request.body()
        return Response(body).with_header("X-Query-Cache-Key", key)

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/html",
        "X-Search-Version": "v1",
    }
    body = b'{"term":"body-remains-readable"}'
    async with TestClient(app) as client:
        first = await client.request("QUERY", "/search", headers=headers, body=body)
        second = await client.request("QUERY", "/search", headers=headers, body=body)

    assert first.status == second.status == 200
    assert first.body == second.body == body
    assert first.header("X-Query-Cache-Key") == second.header("X-Query-Cache-Key")
    assert calls == 2
    assert backend._store == {}
