"""Tests for the plain GET form example."""

from chirp.testing import TestClient


class TestFormGet:
    async def test_search_page_renders_plain_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert '<form action="/" method="get">' in response.text
            assert "Enter a query to search." in response.text

    async def test_query_renders_results_without_htmx(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=chirp")
            assert response.status == 200
            assert "Item 0" in response.text
            assert "Item 2" in response.text
            assert "HX-" not in response.text
