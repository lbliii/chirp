"""Tests for the accessibility example."""

from urllib.parse import urlencode

from chirp.testing import TestClient

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


class TestAccessibilityApp:
    """Verify accessibility example routes and form behavior."""

    async def test_index_renders_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Send feedback" in response.text
            assert "Skip to main content" in response.text
            assert 'id="main"' in response.text
            assert 'aria-label="Feedback form"' in response.text

    async def test_empty_submission_shows_errors(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = urlencode({"name": "", "message": ""}).encode()
            response = await client.post("/feedback", body=body, headers=_FORM_CT)
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_valid_submission_shows_success(self, example_app) -> None:
        async with TestClient(example_app) as client:
            body = urlencode(
                {
                    "name": "Alice",
                    "message": "Great app!",
                }
            ).encode()
            response = await client.post("/feedback", body=body, headers=_FORM_CT)
            assert response.status == 200
            assert "Thank you" in response.text
            assert "Alice" in response.text
