"""Tests for the DocsPlugin standalone example."""

from chirp.testing import TestClient


class TestDocsSite:
    async def test_home_points_to_docs(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "/docs/" in response.text

    async def test_docs_index_uses_local_content_dir(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/docs/")
            assert response.status == 200
            assert "Getting Started" in response.text

    async def test_autodoc_route_is_available(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/docs/api/routes/contacts")
            assert response.status == 200
            assert "Create a new contact" in response.text

    async def test_json_route_still_serves_app_data(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts")
            assert response.status == 200
            assert response.json[0]["name"] == "Alice"
