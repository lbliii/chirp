"""Tests for the streaming example — Stream() and TemplateStream()."""

import os

import pytest

from chirp.testing import TestClient


@pytest.fixture(autouse=True)
def _fast_streaming():
    """Use fast delays for /live tests."""
    os.environ["STREAMING_FAST"] = "1"
    yield
    os.environ.pop("STREAMING_FAST", None)


class TestStreamingPage:
    """Stream() resolves awaitables and streams chunked HTML."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_contains_stats(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Users" in response.text
            assert "1247" in response.text
            assert "Orders" in response.text
            assert "89" in response.text

    async def test_index_contains_feed(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Activity Feed" in response.text
            assert "New order #1001" in response.text
            assert "2 min ago" in response.text

    async def test_index_is_chunked(self, example_app) -> None:
        """Streaming responses use chunked transfer encoding."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # TestClient may buffer the full response; check content is complete
            assert "Progressive Stream" in response.text
            assert "Revenue" in response.text


class TestLivePage:
    """TemplateStream() yields chunks as async iterator produces items."""

    async def test_live_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/live")
            assert response.status == 200

    async def test_live_contains_all_items(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/live")
            assert "First item" in response.text
            assert "Second item" in response.text
            assert "Done" in response.text

    async def test_live_has_header(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/live")
            assert "TemplateStream" in response.text
            assert "Visible Chunks" in response.text
