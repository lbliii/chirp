"""Tests for the hello example."""

from chirp.testing import TestClient


class TestHelloApp:
    """Verify every route in the hello example works through the ASGI pipeline."""

    async def test_index(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert response.text == "Hello, World!"

    async def test_greet_with_path_param(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/greet/alice")
            assert response.status == 200
            assert response.text == "Hello, alice!"

    async def test_greet_different_name(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/greet/bob")
            assert response.text == "Hello, bob!"

    async def test_json_response(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/status")
            assert response.status == 200
            assert "application/json" in response.content_type
            assert '"status"' in response.text
            assert '"ok"' in response.text

    async def test_custom_response_status_and_header(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/custom")
            assert response.status == 201
            assert response.text == "Created"
            assert ("x-custom", "chirp") in response.headers

    async def test_custom_404_handler(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/nonexistent")
            assert response.status == 404
            assert "Nothing at /nonexistent" in response.text
