"""Tests for the mounted-pages shell example."""

from chirp.testing import TestClient


class TestPagesShell:
    async def test_projects_page_renders_full_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/projects")
            assert response.status == 200
            assert "Projects" in response.text
            assert "New project" in response.text
            assert "Apollo" in response.text
            assert 'id="page-content"' in response.text

    async def test_boosted_detail_streams_suspense_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/projects/apollo",
                target="main",
                headers={"HX-Boosted": "true"},
            )
            assert response.status == 200
            assert "Apollo" in response.text
            assert "Loading build stats..." in response.text

    async def test_detail_page_overrides_shell_actions(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/projects/apollo")
            assert response.status == 200
            assert "Deploy" in response.text
            assert "Metrics" in response.text
            assert "New project" not in response.text

    def test_example_app_passes_contract_check(self, example_app) -> None:
        example_app.check()
