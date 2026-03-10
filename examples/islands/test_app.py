"""Tests for the islands example."""

from chirp.testing import TestClient


class TestIslandsPage:
    """GET / renders the islands demo page."""

    async def test_index_returns_200(self, example_app) -> None:
        """Home page renders successfully."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_includes_island_mount_attrs(self, example_app) -> None:
        """Page includes data-island attributes from island_attrs()."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            assert 'data-island="counter"' in html
            assert 'id="counter-root"' in html
            assert 'data-island-src="/static/counter.js"' in html
            assert "data-island-props=" in html

    async def test_includes_ssr_fallback(self, example_app) -> None:
        """Fallback content is present for no-JS mode."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            assert "Count:" in html
            assert "Enable JavaScript to interact" in html
