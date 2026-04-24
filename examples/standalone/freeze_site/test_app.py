"""Tests for the static-freeze standalone example."""

from chirp.testing import TestClient


class TestFreezeSite:
    async def test_home_page_renders_with_layout(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Freeze Demo" in response.text
            assert '<nav class="nav">' in response.text
            assert '<div id="page-root">' in response.text

    async def test_docs_content_renders_from_local_content_dir(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/docs/why-hypermedia")
            assert response.status == 200
            assert "Why Hypermedia" in response.text
