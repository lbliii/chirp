"""Tests for the reactive tasks example."""

import asyncio

from chirp.contracts import check_hypermedia_surface
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

    def test_reactive_contract_metadata_is_clean(self, example_app) -> None:
        result = check_hypermedia_surface(example_app.app)

        assert result.errors == []
        assert result.warnings == []


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

    async def test_mutation_pushes_named_fragment_over_sse(self, example_app) -> None:
        """A mutation must actually push the re-rendered fragment over the wire.

        The reactive bus re-renders the dependent blocks and emits one SSE event
        per block, named after the block (``task_list``, ``task_count``, ...).
        This asserts the *body* of the new task and the *event name* arrive —
        not just the response headers. A regression that broke reactive
        re-render or event naming would pass the headers-only smoke test but
        fail here.
        """
        async with TestClient(example_app.app) as client:

            async def mutate_after_delay():
                await asyncio.sleep(0.1)
                await client.post("/tasks", data={"title": "Pushed via SSE"})
                await asyncio.sleep(0.1)
                example_app.bus.close("board")

            task = asyncio.create_task(mutate_after_delay())
            result = await client.sse("/events", max_events=10)
            await task

            assert result.status == 200
            event_names = {evt.event for evt in result.events}
            # The task_list block re-renders and is pushed under its block name.
            assert "task_list" in event_names
            assert "task_count" in event_names

            task_list_events = [e for e in result.events if e.event == "task_list"]
            assert task_list_events, "expected a task_list SSE event after mutation"
            # The newly added task body must be present in the pushed fragment.
            assert any("Pushed via SSE" in e.data for e in task_list_events)

            # task_count re-renders to reflect the new total (3 seed + 1 = 4).
            count_events = [e for e in result.events if e.event == "task_count"]
            assert count_events
            assert any(">4<" in e.data for e in count_events)
