"""Tests for the kanban example — board rendering, CRUD, move, filter, SSE."""

from chirp.testing import (
    TestClient,
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_hx_trigger,
    assert_is_fragment,
)

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


# ---------------------------------------------------------------------------
# Board rendering
# ---------------------------------------------------------------------------


class TestBoard:
    """GET / returns the Kanban board as a full page or fragment."""

    async def test_index_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html" in response.text
            assert "Kanban Board" in response.text

    async def test_index_contains_all_columns(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'id="column-backlog"' in response.text
            assert 'id="column-in_progress"' in response.text
            assert 'id="column-review"' in response.text
            assert 'id="column-done"' in response.text

    async def test_index_contains_seed_tasks(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "Design landing page" in response.text
            assert "Implement auth flow" in response.text
            assert "Add search indexing" in response.text
            assert "Rate limiting middleware" in response.text

    async def test_index_fragment(self, example_app) -> None:
        """Fragment request returns just the board, not the full page."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/")
            assert_is_fragment(response)
            assert_fragment_contains(response, 'id="board"')
            assert_fragment_not_contains(response, "<html")

    async def test_index_contains_stats(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'id="board-stats"' in response.text
            assert "tasks" in response.text
            assert "high priority" in response.text

    async def test_index_contains_filter_sidebar(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Priority filter checkboxes
            assert 'name="priority"' in response.text
            # Assignee filter should list seed assignees
            assert "Alice" in response.text
            assert "Bob" in response.text
            assert "Carol" in response.text

    async def test_index_contains_kida_features(self, example_app) -> None:
        """Verify Kida template features rendered correctly (no raw tags)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Priority badges rendered via {% match %}
            assert "badge-high" in response.text
            assert "badge-medium" in response.text
            # No raw template syntax leaked
            assert "{%" not in response.text
            assert "{{" not in response.text


# ---------------------------------------------------------------------------
# Add task
# ---------------------------------------------------------------------------


class TestAddTask:
    """POST /tasks — create task with validation and OOB updates."""

    async def test_add_valid(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/tasks",
                body=b"title=New+task&status=backlog&priority=high&assignee=Dave&tags=urgent",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "New task" in response.text

    async def test_add_returns_oob(self, example_app) -> None:
        """Successful add returns OOB fragments with hx-swap-oob."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/tasks",
                body=b"title=OOB+test&status=in_progress&priority=low",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "hx-swap-oob" in response.text

    async def test_add_empty_title_returns_422(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/tasks",
                body=b"title=&status=backlog&priority=medium",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_add_invalid_priority_returns_422(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/tasks",
                body=b"title=Test&status=backlog&priority=critical",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert "Invalid priority" in response.text

    async def test_add_with_optional_fields_empty(self, example_app) -> None:
        """Assignee and tags can be empty."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/tasks",
                body=b"title=Minimal+task&status=backlog&priority=low&assignee=&tags=",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "Minimal task" in response.text
            # Unassigned should appear (via null coalescing)
            assert "Unassigned" in response.text


# ---------------------------------------------------------------------------
# Edit task
# ---------------------------------------------------------------------------


class TestEditTask:
    """GET /tasks/{id}/edit and PUT /tasks/{id}."""

    async def test_edit_form(self, example_app) -> None:
        """GET returns the inline edit form fragment."""
        async with TestClient(example_app) as client:
            response = await client.get("/tasks/1/edit")
            assert response.status == 200
            assert 'name="title"' in response.text
            assert "Design landing page" in response.text

    async def test_edit_form_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/tasks/9999/edit")
            assert response.status == 404

    async def test_save_valid(self, example_app) -> None:
        """PUT with valid data returns OOB updated card + stats."""
        async with TestClient(example_app) as client:
            response = await client.put(
                "/tasks/1",
                body=b"title=Updated+title&description=New+desc&priority=low&assignee=Eve&tags=new",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "Updated title" in response.text

    async def test_save_invalid_empty_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.put(
                "/tasks/1",
                body=b"title=&description=test&priority=high&assignee=&tags=",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_save_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.put(
                "/tasks/9999",
                body=b"title=Test&description=&priority=low&assignee=&tags=",
                headers=_FORM_CT,
            )
            assert response.status == 404


# ---------------------------------------------------------------------------
# Move task
# ---------------------------------------------------------------------------


class TestMoveTask:
    """POST /tasks/{id}/move/{status} — move between columns."""

    async def test_move_to_adjacent(self, example_app) -> None:
        """Move task 1 (done → review) returns OOB with both columns."""
        async with TestClient(example_app) as client:
            response = await client.post("/tasks/1/move/review")
            assert response.status == 200
            assert "hx-swap-oob" in response.text
            # Both source and destination columns should be in the response
            assert 'id="column-done"' in response.text
            assert 'id="column-review"' in response.text

    async def test_move_invalid_status(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/tasks/1/move/invalid")
            assert response.status == 400

    async def test_move_same_column(self, example_app) -> None:
        """Moving to the same column is rejected."""
        async with TestClient(example_app) as client:
            # Task 1 is in "done"
            response = await client.post("/tasks/1/move/done")
            assert response.status == 400

    async def test_move_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/tasks/9999/move/backlog")
            assert response.status == 404

    async def test_move_updates_stats(self, example_app) -> None:
        """Move response includes the stats bar OOB fragment."""
        async with TestClient(example_app) as client:
            response = await client.post("/tasks/1/move/review")
            assert 'id="board-stats"' in response.text


# ---------------------------------------------------------------------------
# Delete task
# ---------------------------------------------------------------------------


class TestDeleteTask:
    """DELETE /tasks/{id} — remove task and fire HX-Trigger."""

    async def test_delete(self, example_app) -> None:
        """Delete removes the task and returns updated column."""
        async with TestClient(example_app) as client:
            response = await client.delete("/tasks/1")
            assert response.status == 200
            # Task 1 ("Design landing page") should no longer appear
            assert "Design landing page" not in response.text

    async def test_delete_fires_trigger(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.delete("/tasks/1")
            assert_hx_trigger(response, "taskDeleted")

    async def test_delete_returns_oob(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.delete("/tasks/1")
            assert "hx-swap-oob" in response.text

    async def test_delete_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.delete("/tasks/9999")
            assert response.status == 404


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


class TestFilter:
    """GET /filter — filter board by priority, assignee, tag."""

    async def test_filter_by_priority(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/filter?priority=high")
            assert response.status == 200
            # High-priority tasks should be present
            assert "Implement auth flow" in response.text
            # Low-priority tasks should not be in filtered results
            assert "Dark mode toggle" not in response.text

    async def test_filter_by_assignee(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/filter?assignee=Alice")
            assert response.status == 200
            assert "Design landing page" in response.text
            assert "Add search indexing" in response.text
            # Bob's tasks should not appear
            assert "Set up CI pipeline" not in response.text

    async def test_filter_by_tag(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/filter?tag=security")
            assert response.status == 200
            assert "Implement auth flow" in response.text
            assert "Rate limiting middleware" in response.text
            # Non-security tasks should not appear
            assert "Dashboard charts" not in response.text

    async def test_filter_no_results(self, example_app) -> None:
        """Filter that matches nothing returns empty columns."""
        async with TestClient(example_app) as client:
            response = await client.get("/filter?assignee=Nobody")
            assert response.status == 200
            assert "no tasks" in response.text.lower()


# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------


class TestSSE:
    """GET /events — live updates via Server-Sent Events."""

    async def test_sse_returns_events(self, example_app) -> None:
        """SSE stream emits fragment events with OOB swaps."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=3)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) >= 3

    async def test_sse_events_are_fragments(self, example_app) -> None:
        """Fragment events contain rendered HTML, not raw template syntax."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=3)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        assert len(fragment_events) >= 3
        for evt in fragment_events:
            assert "{{" not in evt.data
            assert "{%" not in evt.data

    async def test_sse_includes_oob_swaps(self, example_app) -> None:
        """SSE fragment events include hx-swap-oob for targeted updates."""
        async with TestClient(example_app) as client:
            result = await client.sse("/events", max_events=3)
        fragment_events = [e for e in result.events if e.event == "fragment"]
        oob_events = [e for e in fragment_events if "hx-swap-oob" in e.data]
        assert len(oob_events) >= 1
