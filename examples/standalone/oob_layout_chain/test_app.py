"""Tests for oob_layout_chain example."""

from chirp.testing import TestClient


async def test_full_page_renders(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.get("/")
        assert response.status == 200
        assert "Welcome to the OOB layout chain example" in response.text
        assert 'id="main"' in response.text


async def test_fragment_request(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.fragment("/")
        assert response.status == 200
        assert "Welcome" in response.text or "card" in response.text
