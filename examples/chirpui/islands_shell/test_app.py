"""Tests for the islands_shell example."""

from chirp.testing import TestClient


class TestIslandsShell:
    """Islands + app shell renders and navigates."""

    async def test_home_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_home_has_island(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            assert 'data-island="counter"' in html
            assert 'data-island-src="/static/counter.js"' in html

    async def test_dashboard_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/dashboard")
            assert response.status == 200

    async def test_about_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/about")
            assert response.status == 200

    async def test_about_has_no_island(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/about")
            assert 'data-island="counter"' not in response.text


class TestIslandFragmentRemount:
    """A boosted navigation returns the island mount markup so the client
    adapter can remount the island after htmx swaps the shell.

    This is the headline feature of the example: islands coexist with the app
    shell and remount cleanly on navigation. The fragment endpoint must carry
    the full mount contract — the island name, mount id, adapter src, and the
    serialized props — not just the inner static fallback content. A regression
    that dropped island markup from fragment responses would still pass the
    full-page smoke test but break remount.
    """

    async def test_boosted_navigation_returns_island_mount_markup(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/",
                target="main",
                headers={"HX-Boosted": "true"},
            )
            assert response.status == 200
            html = response.text
            # Fragment, not a full document.
            assert "<html" not in html
            # Full island mount contract is present for the client adapter.
            assert 'data-island="counter"' in html
            assert 'id="counter-root"' in html
            assert 'data-island-src="/static/counter.js"' in html
            # Props are serialized so the island remounts with its initial state.
            assert "data-island-props=" in html
            assert "initial_count" in html

    async def test_plain_fragment_returns_island_mount_markup(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment("/", target="page-content")
            assert response.status == 200
            assert 'data-island="counter"' in response.text
            assert 'id="counter-root"' in response.text
