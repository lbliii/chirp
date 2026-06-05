"""Tests for the shell_oob example (Team Settings Console).

Smoke coverage for the mounted-pages chirp-ui shell: every page renders, and
the app passes the hypermedia contract check.
"""

from chirp.testing import TestClient


class TestShellOOB:
    async def test_dashboard_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Dashboard" in response.text
            assert "Total Settings" in response.text

    async def test_settings_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/settings")
            assert response.status == 200

    async def test_about_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/about")
            assert response.status == 200

    def test_example_app_passes_contract_check(self, example_app) -> None:
        example_app.check()
