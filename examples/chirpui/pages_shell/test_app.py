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
            assert "chirpui-nav-tree--linked-branches" in response.text

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
            # #main selects the shell outlet (#page-content); page_root still must be present inside it
            assert 'id="page-content"' in response.text
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


class TestSuspenseDeferredStats:
    """Drain the chunked Suspense response and assert the *resolved* deferred
    values stream in after the shell — not just the skeleton placeholders.

    The detail page defers ``stats`` and ``activity`` (see page.py). The shell
    renders first with skeleton placeholders, then each deferred block streams
    as a swap wrapped in a ``<template id="_chirp_d_...">`` element appended
    after ``</html>``. A regression that dropped the deferred resolve would
    still pass the shell-only smoke test but fail here.
    """

    async def test_resolved_stats_stream_in_after_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/projects/apollo")
            assert response.status == 200
            html = response.text

            # Shell renders first: skeleton placeholders appear before </html>.
            end_of_shell = html.find("</html>")
            assert end_of_shell != -1
            assert "chirpui-skeleton" in html[:end_of_shell]

            # Deferred blocks stream in after the shell, wrapped in OOB templates
            # keyed to the defer_map targets.
            assert "_chirp_d_project-stats" in html
            assert "_chirp_d_project-activity" in html

            deferred_tail = html[end_of_shell:]
            # Resolved stat values (from _load_stats) — not present in the shell.
            assert "42 ms" in deferred_tail
            assert "18 this week" in deferred_tail
            assert "99.98%" in deferred_tail
            # Resolved activity (from _load_activity) interpolates the project name.
            assert "passed layout-chain smoke tests" in deferred_tail

    async def test_shell_does_not_contain_resolved_values(self, example_app) -> None:
        """The shell itself must show skeletons, not resolved stats.

        Guards against a regression where deferred values are resolved eagerly
        into the shell (defeating the instant-shell point of Suspense).
        """
        async with TestClient(example_app) as client:
            response = await client.get("/projects/apollo")
            html = response.text
            end_of_shell = html.find("</html>")
            assert end_of_shell != -1
            shell = html[:end_of_shell]
            assert "42 ms" not in shell
            assert "passed layout-chain smoke tests" not in shell
