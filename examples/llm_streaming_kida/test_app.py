"""Tests for llm_streaming_kida — TemplateStream with {% async for %}."""

from chirp.testing import TestClient


class TestIndex:
    """The form page renders."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_has_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'action="/ask"' in response.text
            assert 'name="prompt"' in response.text


class TestAskStream:
    """TemplateStream yields chunked HTML from {% async for %}."""

    async def test_ask_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                data={"prompt": "What is Kida?"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200

    async def test_ask_streams_response(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                data={"prompt": "test"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # Simulated stream yields: "Kida is a modern template engine..."
            assert "Kida" in response.text
            assert "template engine" in response.text
            assert "{% async for %}" in response.text

    async def test_ask_includes_prompt(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/ask",
                data={"prompt": "Hello"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert "You asked: Hello" in response.text
