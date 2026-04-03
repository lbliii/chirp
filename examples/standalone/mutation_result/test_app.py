"""Tests for the MutationResult example."""

from chirp.testing import TestClient


class TestIndex:
    async def test_full_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Tasks" in response.text
            assert "Buy groceries" in response.text

    async def test_shows_initial_tasks(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Buy groceries" in response.text
            assert "Write docs" in response.text
            assert "Review PR" in response.text


class TestAddTask:
    async def test_htmx_post_returns_fragment(self, example_app) -> None:
        """htmx POST gets rendered fragments, not a redirect."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/tasks",
                body=b"text=New+task",
                headers={
                    "content-type": "application/x-www-form-urlencoded",
                    "hx-request": "true",
                },
            )
            assert response.status == 200
            assert "New task" in response.text

    async def test_plain_post_redirects(self, example_app) -> None:
        """Non-htmx POST gets 303 redirect."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/tasks",
                body=b"text=New+task",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 303


class TestDeleteTask:
    async def test_htmx_delete_returns_fragment(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.request(
                "DELETE",
                "/tasks/1",
                headers={"hx-request": "true"},
            )
            assert response.status == 200
            assert "Buy groceries" not in response.text

    async def test_plain_delete_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.request(
                "DELETE",
                "/tasks/1",
            )
            assert response.status == 303


class TestToggleTask:
    async def test_htmx_patch_returns_fragment(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.request(
                "PATCH",
                "/tasks/1/toggle",
                headers={"hx-request": "true"},
            )
            assert response.status == 200
            assert "task-list" in response.text

    async def test_plain_patch_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.request(
                "PATCH",
                "/tasks/1/toggle",
            )
            assert response.status == 303
