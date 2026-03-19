"""Tests for the theming example."""

from chirp.testing import TestClient


class TestThemingRoutes:
    """Verify both pages render and contain theming infrastructure."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_about_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/about")
            assert response.status == 200

    async def test_index_has_theme_toggle(self, example_app) -> None:
        """The toggle button is present in the rendered HTML."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'id="theme-toggle"' in response.text

    async def test_index_has_css_custom_properties(self, example_app) -> None:
        """CSS custom properties for theming are in the page."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "--bg:" in response.text
            assert "--fg:" in response.text
            assert "--surface:" in response.text

    async def test_index_has_prefers_color_scheme(self, example_app) -> None:
        """The prefers-color-scheme media query is present."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "prefers-color-scheme: dark" in response.text

    async def test_index_has_data_theme_overrides(self, example_app) -> None:
        """Explicit data-theme selectors are present for user override."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert '[data-theme="light"]' in response.text
            assert '[data-theme="dark"]' in response.text

    async def test_index_has_anti_fouc_script(self, example_app) -> None:
        """The inline script that applies the stored theme is in <head>."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'localStorage.getItem("theme")' in response.text

    async def test_about_inherits_theme_infrastructure(self, example_app) -> None:
        """The about page inherits the full theme setup from base.html."""
        async with TestClient(example_app) as client:
            response = await client.get("/about")
            assert 'id="theme-toggle"' in response.text
            assert "prefers-color-scheme: dark" in response.text
            assert "--bg:" in response.text
