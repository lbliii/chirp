"""Tests for the shell_oob example (Team Settings Console).

Smoke coverage for the mounted-pages chirp-ui shell: every page renders, and
the app passes the hypermedia contract check. Behavior coverage exercises the
headline feature — toggling a setting changes the dashboard stats on the next
navigation.
"""

import re

from chirp.testing import TestClient


def _stat_value(html: str, label: str) -> int | None:
    """Read a chirp-ui metric-card stat value by its ``label`` text.

    Returns the integer rendered in the ``chirpui-stat__value`` span that
    immediately precedes the matching ``chirpui-stat__label``.
    """
    match = re.search(
        r'chirpui-stat__value">(\d+)</span>\s*'
        r'<span class="chirpui-stat__label">' + re.escape(label),
        html,
    )
    return int(match.group(1)) if match else None


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


class TestSettingsToggleUpdatesDashboard:
    """Headline feature: toggling a setting flips the dashboard stats.

    ``slack_alerts`` ships disabled in the seed store, so toggling it moves one
    setting from the disabled column to the enabled column. A fresh GET of the
    dashboard must reflect the new counts (cross-page state via the store).
    """

    async def test_toggle_enables_setting_and_updates_stats(self, example_app) -> None:
        async with TestClient(example_app) as client:
            before = await client.get("/")
            enabled_before = _stat_value(before.text, "Enabled")
            disabled_before = _stat_value(before.text, "Disabled")
            assert enabled_before is not None
            assert disabled_before is not None

            # slack_alerts is seeded disabled — toggling it should enable it.
            toggle = await client.post(
                "/settings",
                data={"key": "slack_alerts"},
                headers={"HX-Request": "true", "HX-Target": "page-root"},
            )
            assert toggle.status == 200

            after = await client.get("/")
            assert _stat_value(after.text, "Enabled") == enabled_before + 1
            assert _stat_value(after.text, "Disabled") == disabled_before - 1

    async def test_toggle_twice_restores_stats(self, example_app) -> None:
        async with TestClient(example_app) as client:
            before = await client.get("/")
            enabled_before = _stat_value(before.text, "Enabled")
            assert enabled_before is not None

            for _ in range(2):
                resp = await client.post(
                    "/settings",
                    data={"key": "slack_alerts"},
                    headers={"HX-Request": "true", "HX-Target": "page-root"},
                )
                assert resp.status == 200

            after = await client.get("/")
            assert _stat_value(after.text, "Enabled") == enabled_before
