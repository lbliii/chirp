"""Tests for the Suspense dashboard example."""

from chirp.testing import TestClient


class TestSuspenseDashboard:
    """Verify the Suspense streaming response works end-to-end."""

    async def test_dashboard_returns_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200

    async def test_dashboard_contains_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Sales Dashboard" in response.text

    async def test_dashboard_contains_revenue_data(self, example_app) -> None:
        """Revenue block should resolve with real data (not skeleton)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # The streamed response should contain the resolved revenue
            assert "$" in response.text

    async def test_dashboard_contains_orders_table(self, example_app) -> None:
        """Orders block should resolve with real data."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Should have order IDs in the resolved output
            assert "#100" in response.text

    async def test_dashboard_contains_visitors(self, example_app) -> None:
        """Visitors block should resolve with real data."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Peak today" in response.text
