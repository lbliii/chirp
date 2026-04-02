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

    async def test_boosted_detail_streams_suspense_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/projects/apollo",
                target="main",
                headers={"HX-Boosted": "true"},
            )
            assert response.status == 200
            assert "Apollo" in response.text
            assert "project-stats" in response.text
            # hx-select="#page-root" on #main — fragment must include this id or swaps are empty
            assert 'id="page-root"' in response.text

    async def test_detail_page_overrides_shell_actions(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/projects/apollo")
            assert response.status == 200
            assert "Deploy" in response.text
            assert "Metrics" in response.text
            assert "New project" not in response.text

    async def test_settings_page_replaces_shell_actions(self, example_app) -> None:
        """Settings subroute uses mode='replace' — only Save/Cancel, no inherited actions."""
        async with TestClient(example_app) as client:
            response = await client.get("/projects/apollo/settings")
            assert response.status == 200
            assert "Save" in response.text
            assert "Cancel" in response.text
            assert "Project settings" in response.text
            # mode=replace: topbar has Save/Cancel only (no Deploy/Metrics from parent)
            html = response.text
            topbar_end = html.find("chirpui-app-shell__topbar-end")
            main_start = html.find('<main id="main"')
            if topbar_end != -1 and main_start != -1:
                topbar_section = html[topbar_end:main_start]
                assert "Deploy" not in topbar_section
                assert "Metrics" not in topbar_section

    def test_example_app_passes_contract_check(self, example_app) -> None:
        example_app.check()
