"""Tests for the islands_swap example."""

from chirp.testing import TestClient


class TestIslandsSwap:
    """Islands + htmx swap renders and serves fragment."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_has_load_button(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Load widget" in response.text
            assert 'hx-get="/widget"' in response.text

    async def test_index_has_no_island_on_load(self, example_app) -> None:
        """Island should not be visible until Load widget is clicked."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'data-island="counter"' not in response.text

    async def test_widget_fragment_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/widget")
            assert response.status == 200

    async def test_widget_fragment_has_island(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/widget")
            html = response.text
            assert 'data-island="counter"' in html
            assert 'data-island-src="/static/counter.js"' in html
