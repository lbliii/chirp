"""Tests for the static site dev server example."""

from chirp.testing import TestClient


class TestStaticSitePages:
    """Static pages are served from public/ with HTML injection."""

    async def test_index_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<h1>Static Site</h1>" in response.text
            # HTMLInject should have added the reload script
            assert "EventSource" in response.text
            assert "__reload__" in response.text

    async def test_docs_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/docs/")
            assert response.status == 200
            assert "<h1>Documentation</h1>" in response.text
            assert "EventSource" in response.text

    async def test_css_not_injected(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/style.css")
            assert response.status == 200
            assert "text/css" in response.content_type
            assert "EventSource" not in response.text

    async def test_custom_404(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/nonexistent")
            assert response.status == 404
            assert "404" in response.text


class TestStaticSiteCaching:
    """Dev mode serves with no-cache headers."""

    async def test_no_cache_header(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            cc = [v for name, v in response.headers if name == "cache-control"]
            assert cc == ["no-cache"]


class TestReloadEndpoint:
    """The SSE reload endpoint is accessible."""

    async def test_reload_endpoint_connects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # SSE endpoint should accept connections (we read 0 events)
            result = await client.sse("/__reload__", max_events=0)
            assert result.status == 200
            assert result.headers.get("content-type") == "text/event-stream"
