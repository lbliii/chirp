"""Tests for the reactive tasks example."""

from chirp.testing import TestClient


class TestPageRender:
    """The board page renders correctly."""

    async def test_index_renders_full_page(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html>" in response.text
            assert "<h1>Reactive Tasks</h1>" in response.text
            assert 'sse-connect="/events"' in response.text
            # All sse-swap elements must be inside the sse-connect div
            assert 'id="task_list"' in response.text
            assert 'id="task_count"' in response.text
            assert 'id="presence_count"' in response.text
            assert 'id="last_update"' in response.text

    async def test_index_shows_seed_tasks(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            response = await client.get("/")
            assert "Try the reactive demo" in response.text
            assert "Open a second tab" in response.text
            assert "Watch it update" in response.text

    async def test_index_shows_task_count(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            response = await client.get("/")
            assert "badge" in response.text


class TestMutations:
    """POST/DELETE routes mutate data and return fragments."""

    async def test_add_task(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            response = await client.post("/tasks", data={"title": "New task"})
            assert response.status == 200
            assert "New task" in response.text

    async def test_add_empty_title_returns_error(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            response = await client.post("/tasks", data={"title": ""})
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_toggle_task(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            response = await client.post("/tasks/1/toggle")
            assert response.status == 200
            # Task 1 should now show "undo" (was "done")
            assert "undo" in response.text

    async def test_delete_task(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            response = await client.delete("/tasks/1")
            assert response.status == 200
            assert "Try the reactive demo" not in response.text


class TestSSEStream:
    """The /events endpoint streams reactive updates."""

    async def test_events_endpoint_returns_sse(self, example_app) -> None:
        async with TestClient(example_app.app) as client:
            # Trigger a mutation so the stream has something to push
            import asyncio

            async def mutate_after_delay():
                await asyncio.sleep(0.1)
                await client.post("/tasks", data={"title": "SSE test"})
                await asyncio.sleep(0.1)
                example_app.bus.close("board")

            task = asyncio.create_task(mutate_after_delay())
            result = await client.sse("/events", max_events=10)
            await task

            assert result.status == 200
            assert result.headers.get("content-type") == "text/event-stream"
