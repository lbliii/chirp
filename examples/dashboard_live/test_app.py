"""Tests for the dashboard_live example — chirp.data showcase."""

from chirp.testing import TestClient


class TestDashboardPage:
    """GET / renders the full dashboard with live data from the database."""

    async def test_index_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_index_contains_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Live Sales Dashboard" in response.text

    async def test_index_renders_stats_bar(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'id="stats"' in response.text
            assert "Total Orders" in response.text
            assert "Revenue" in response.text
            assert "Pending" in response.text
            assert "Avg Order" in response.text

    async def test_index_renders_orders_table(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'id="orders"' in response.text
            assert "<th>#</th>" in response.text
            assert "<th>Customer</th>" in response.text
            assert "<th>Product</th>" in response.text

    async def test_index_has_seeded_data(self, example_app) -> None:
        """The on_startup hook seeds 12 orders into the database."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Stats should show non-zero values from seeded data
            assert "Total Orders" in response.text
            # The orders table should have rows (seeded data)
            assert '<td class="amount">' in response.text

    async def test_index_contains_sse_connection(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'sse-connect="/events"' in response.text

    async def test_index_no_raw_template_tags(self, example_app) -> None:
        """Template is fully rendered — no Jinja syntax leaks."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "{{" not in response.text


class TestDashboardSSE:
    """Live order updates stream through SSE.

    The SSE generator sleeps 2-5 seconds between events, so we use
    timeout to bound the test duration rather than waiting for a
    fixed max_events count.
    """

    async def test_receives_events(self, example_app) -> None:
        """Events arrive within the timeout window."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=2, timeout=8.0)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) >= 1

    async def test_events_are_fragments(self, example_app) -> None:
        """SSE events are rendered HTML fragments, not raw templates."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=2, timeout=8.0)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        assert len(fragment_events) >= 1
        for evt in fragment_events:
            assert "{{" not in evt.data
