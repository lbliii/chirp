"""Tests for the islands_shell example."""

from chirp.testing import TestClient


class TestIslandsShell:
    """Islands + app shell renders and navigates."""

    async def test_home_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_home_has_island(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            assert 'data-island="counter"' in html
            assert 'data-island-src="/static/counter.js"' in html

    async def test_dashboard_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/dashboard")
            assert response.status == 200

    async def test_about_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/about")
            assert response.status == 200

    async def test_about_has_no_island(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/about")
            assert 'data-island="counter"' not in response.text
