"""Tests for the kanban_shell example — auth, board rendering, CRUD, move, filter, SSE."""

import re
from unittest.mock import AsyncMock, patch

from chirp.testing import (
    TestClient,
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_hx_trigger,
    assert_is_fragment,
)

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


# ---------------------------------------------------------------------------
# Auth helpers (CSRF-aware)
# ---------------------------------------------------------------------------


def _extract_cookie(response, name: str = "chirp_session_kanban_shell") -> str | None:
    """Extract a Set-Cookie value from response headers."""
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


def _extract_csrf_token(html: str) -> str | None:
    """Extract CSRF token from a rendered form (hidden input) or meta tag."""
    patterns = (
        r'<input[^>]*name="_csrf_token"[^>]*value="([^"]+)"',
        r'<input[^>]*value="([^"]+)"[^>]*name="_csrf_token"',
        r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"',
        r'<meta[^>]*content="([^"]+)"[^>]*name="csrf-token"',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def _extract_csrf_meta(html: str) -> str | None:
    """Extract CSRF token from a meta tag (for htmx requests)."""
    return _extract_csrf_token(html)


def _assert_hx_reselect_star(response) -> None:
    """Fragments should override inherited shell hx-select."""
    assert response.header("HX-Reselect") == "*"


async def _login(client, username: str = "alice") -> dict[str, str]:
    """Log in (CSRF-aware) and return auth + CSRF headers for subsequent requests."""
    page = await client.get("/login")
    session_cookie = _extract_cookie(page)
    csrf_token = _extract_csrf_token(page.text)

    headers = {**_FORM_CT}
    if session_cookie:
        headers["Cookie"] = f"chirp_session_kanban_shell={session_cookie}"

    body = f"username={username}&password=password"
    if csrf_token:
        body += f"&_csrf_token={csrf_token}"

    r = await client.post("/login", body=body.encode(), headers=headers)
    cookie = _extract_cookie(r) or session_cookie
    assert cookie is not None, f"Login failed for {username}"

    board = await client.get("/", headers={"Cookie": f"chirp_session_kanban_shell={cookie}"})
    board_cookie = _extract_cookie(board) or cookie
    fresh_csrf = _extract_csrf_meta(board.text) or csrf_token

    auth_headers: dict[str, str] = {"Cookie": f"chirp_session_kanban_shell={board_cookie}"}
    if fresh_csrf:
        auth_headers["X-CSRF-Token"] = fresh_csrf
    return auth_headers


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    """Login, logout, and protected route behaviour."""

    async def test_board_redirects_to_login(self, example_app) -> None:
        """Unauthenticated GET / returns 302 to /login."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 302
            assert "/login" in response.header("location", "")

    async def test_login_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/login")
            assert response.status == 200
            assert "username" in response.text.lower()
            assert "password" in response.text.lower()

    async def test_valid_login_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/login")
            session = _extract_cookie(page)
            csrf = _extract_csrf_token(page.text)
            headers = {**_FORM_CT}
            if session:
                headers["Cookie"] = f"chirp_session_kanban_shell={session}"
            body = b"username=alice&password=password"
            if csrf:
                body += f"&_csrf_token={csrf}".encode()
            response = await client.post("/login", body=body, headers=headers)
            assert response.status == 302
            assert response.header("location") == "/"

    async def test_invalid_login_shows_error(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/login")
            session = _extract_cookie(page)
            csrf = _extract_csrf_token(page.text)
            headers = {**_FORM_CT}
            if session:
                headers["Cookie"] = f"chirp_session_kanban_shell={session}"
            body = b"username=alice&password=wrong"
            if csrf:
                body += f"&_csrf_token={csrf}".encode()
            response = await client.post("/login", body=body, headers=headers)
            assert response.status == 200
            assert "Invalid" in response.text

    async def test_logout_redirects_to_login(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post(
                "/logout",
                headers={**_FORM_CT, **auth},
                body=b"",
            )
            assert response.status == 302
            assert "/login" in response.header("location", "")

    async def test_all_demo_users_can_login(self, example_app) -> None:
        """Alice, Bob, and Carol can all log in."""
        async with TestClient(example_app) as client:
            for name in ("alice", "bob", "carol"):
                page = await client.get("/login")
                session = _extract_cookie(page)
                csrf = _extract_csrf_token(page.text)
                headers = {**_FORM_CT}
                if session:
                    headers["Cookie"] = f"chirp_session_kanban_shell={session}"
                body = f"username={name}&password=password"
                if csrf:
                    body += f"&_csrf_token={csrf}"
                r = await client.post("/login", body=body.encode(), headers=headers)
                assert r.status == 302, f"{name} login failed"
                assert _extract_cookie(r) is not None or session is not None

    async def test_current_user_shown_in_header(self, example_app) -> None:
        """Board shows logged-in user's name in the header."""
        async with TestClient(example_app) as client:
            auth = await _login(client, "bob")
            response = await client.get("/", headers=auth)
            assert response.status == 200
            assert "Bob" in response.text
            assert "kanban-user-info" in response.text

    async def test_own_cards_highlighted(self, example_app) -> None:
        """Cards assigned to the logged-in user get the 'you' badge."""
        async with TestClient(example_app) as client:
            auth = await _login(client, "alice")
            response = await client.get("/", headers=auth)
            assert response.status == 200
            assert "kanban-card__you" in response.text
            assert "kanban-card--mine" in response.text


# ---------------------------------------------------------------------------
# Board rendering
# ---------------------------------------------------------------------------


class TestBoard:
    """GET / returns the Kanban board as a full page or fragment."""

    async def test_index_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/", headers=auth)
            assert response.status == 200
            assert "<html" in response.text
            assert "Kanban Board" in response.text

    async def test_index_contains_all_columns(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/", headers=auth)
            assert 'id="column-backlog"' in response.text
            assert 'id="column-in_progress"' in response.text
            assert 'id="column-review"' in response.text
            assert 'id="column-done"' in response.text

    async def test_index_contains_seed_tasks(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/", headers=auth)
            assert "Design landing page" in response.text
            assert "Implement auth flow" in response.text
            assert "Add search indexing" in response.text
            assert "Rate limiting middleware" in response.text

    async def test_index_fragment(self, example_app) -> None:
        """Fragment request with HX-Target returns just the board, not full page."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.fragment("/", target="main", headers=auth)
            assert_is_fragment(response)
            assert_fragment_contains(response, 'id="board"')
            assert_fragment_not_contains(response, "<html")

    async def test_index_boosted_fragment_keeps_page_content_contract(self, example_app) -> None:
        """Boosted app-shell navigations still override inherited shell selection."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.fragment(
                "/",
                target="main",
                headers={**auth, "HX-Boosted": "true"},
            )
            assert_is_fragment(response)
            assert_fragment_contains(response, 'id="board"')
            _assert_hx_reselect_star(response)

    async def test_index_contains_stats(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/", headers=auth)
            assert 'id="board-stats"' in response.text
            assert "tasks" in response.text
            assert "high priority" in response.text

    async def test_index_contains_filter_sidebar(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/", headers=auth)
            assert 'name="priority"' in response.text
            assert "Alice" in response.text
            assert "Bob" in response.text
            assert "Carol" in response.text

    async def test_index_contains_kida_features(self, example_app) -> None:
        """Verify Kida template features rendered correctly (no raw tags)."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/", headers=auth)
            assert "chirpui-badge" in response.text or "badge" in response.text
            assert "{%" not in response.text
            assert "{{" not in response.text


# ---------------------------------------------------------------------------
# Add task
# ---------------------------------------------------------------------------


class TestAddTask:
    """POST /tasks — create task with validation and OOB updates."""

    async def test_add_valid(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post(
                "/tasks",
                body=b"title=New+task&status=backlog&priority=high&assignee=Dave&tags=urgent",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 200
            assert "New task" in response.text

    async def test_add_returns_oob(self, example_app) -> None:
        """Successful add returns OOB fragments with hx-swap-oob."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post(
                "/tasks",
                body=b"title=OOB+test&status=in_progress&priority=low",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 200
            assert "hx-swap-oob" in response.text

    async def test_add_empty_title_returns_422(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.fragment(
                "/tasks",
                method="POST",
                target="add-form",
                body=b"title=&status=backlog&priority=medium",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 422
            assert "required" in response.text.lower()
            _assert_hx_reselect_star(response)

    async def test_add_invalid_priority_returns_422(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post(
                "/tasks",
                body=b"title=Test&status=backlog&priority=critical",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 422
            assert "Invalid priority" in response.text

    async def test_add_auto_assigns_current_user(self, example_app) -> None:
        """When assignee is empty, auto-assigns the logged-in user."""
        async with TestClient(example_app) as client:
            auth = await _login(client, "bob")
            response = await client.post(
                "/tasks",
                body=b"title=Auto+assign+test&status=backlog&priority=low&assignee=&tags=",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 200
            assert "Bob" in response.text


# ---------------------------------------------------------------------------
# Edit task
# ---------------------------------------------------------------------------


class TestEditTask:
    """GET /tasks/{id}/edit and PUT /tasks/{id}."""

    async def test_edit_form(self, example_app) -> None:
        """GET returns the inline edit form fragment."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.fragment("/tasks/1/edit", target="task-1", headers=auth)
            assert response.status == 200
            assert 'name="title"' in response.text
            assert "Design landing page" in response.text
            _assert_hx_reselect_star(response)

    async def test_edit_form_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/tasks/9999/edit", headers=auth)
            assert response.status == 404

    async def test_save_valid(self, example_app) -> None:
        """PUT with valid data returns OOB updated card + stats."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.put(
                "/tasks/1",
                body=b"title=Updated+title&description=New+desc&priority=low&assignee=Eve&tags=new",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 200
            assert "Updated title" in response.text

    async def test_save_invalid_empty_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.fragment(
                "/tasks/1",
                method="PUT",
                target="task-1",
                body=b"title=&description=test&priority=high&assignee=&tags=",
                headers={**_FORM_CT, **auth},
            )
            assert response.status == 422
            assert "required" in response.text.lower()
            _assert_hx_reselect_star(response)

    async def test_save_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.put(
                "/tasks/9999",
                body=b"title=Test&description=&priority=low&assignee=&tags=",
                headers={**_FORM_CT, **auth},
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
            auth = await _login(client)
            response = await client.post("/tasks/1/move/review", headers=auth)
            assert response.status == 200
            assert "hx-swap-oob" in response.text
            assert 'id="column-done"' in response.text
            assert 'id="column-review"' in response.text

    async def test_move_invalid_status(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post("/tasks/1/move/invalid", headers=auth)
            assert response.status == 400

    async def test_move_same_column(self, example_app) -> None:
        """Moving to the same column is rejected."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post("/tasks/1/move/done", headers=auth)
            assert response.status == 400

    async def test_move_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post("/tasks/9999/move/backlog", headers=auth)
            assert response.status == 404

    async def test_move_updates_stats(self, example_app) -> None:
        """Move response includes the stats bar OOB fragment."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.post("/tasks/1/move/review", headers=auth)
            assert 'id="board-stats"' in response.text


# ---------------------------------------------------------------------------
# Delete task
# ---------------------------------------------------------------------------


class TestDeleteTask:
    """DELETE /tasks/{id} — remove task and fire HX-Trigger."""

    async def test_delete(self, example_app) -> None:
        """Delete removes the task and returns updated column."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.delete("/tasks/1", headers=auth)
            assert response.status == 200
            assert "Design landing page" not in response.text

    async def test_delete_fires_trigger(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.delete("/tasks/1", headers=auth)
            assert_hx_trigger(response, "taskDeleted")

    async def test_delete_returns_oob(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.delete("/tasks/1", headers=auth)
            assert "hx-swap-oob" in response.text

    async def test_delete_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.delete("/tasks/9999", headers=auth)
            assert response.status == 404


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


class TestFilter:
    """GET /filter — filter board by priority, assignee, tag."""

    async def test_filter_by_priority(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.fragment("/filter?priority=high", target="board", headers=auth)
            assert response.status == 200
            assert "Implement auth flow" in response.text
            assert "Dark mode toggle" not in response.text
            _assert_hx_reselect_star(response)

    async def test_filter_by_assignee(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/filter?assignee=Alice", headers=auth)
            assert response.status == 200
            assert "Design landing page" in response.text
            assert "Add search indexing" in response.text
            assert "Set up CI pipeline" not in response.text

    async def test_filter_by_tag(self, example_app) -> None:
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/filter?tag=security", headers=auth)
            assert response.status == 200
            assert "Implement auth flow" in response.text
            assert "Rate limiting middleware" in response.text
            assert "Dashboard charts" not in response.text

    async def test_filter_no_results(self, example_app) -> None:
        """Filter that matches nothing returns empty columns."""
        async with TestClient(example_app) as client:
            auth = await _login(client)
            response = await client.get("/filter?assignee=Nobody", headers=auth)
            assert response.status == 200
            assert "no tasks" in response.text.lower()


# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------


class TestSSE:
    """GET /events — live updates via Server-Sent Events."""

    async def test_sse_returns_events(self, example_app) -> None:
        """SSE stream emits fragment events with OOB swaps."""
        with (
            patch("app.random_move") as mock_move,
            patch("app.asyncio.sleep", new_callable=AsyncMock),
        ):
            from dataclasses import replace

            from store import COLUMNS, get_tasks

            tasks = get_tasks()
            if tasks:
                t = tasks[0]
                new_status = next((s for s in dict(COLUMNS) if s != t.status), t.status)
                mock_move.return_value = (replace(t, status=new_status), t.status)
            async with TestClient(example_app) as client:
                auth = await _login(client)
                result = await client.sse("/events", max_events=3, headers=auth)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) >= 3

    async def test_sse_events_are_fragments(self, example_app) -> None:
        """Fragment events contain rendered HTML, not raw template syntax."""
        with (
            patch("app.random_move") as mock_move,
            patch("app.asyncio.sleep", new_callable=AsyncMock),
        ):
            from dataclasses import replace

            from store import COLUMNS, get_tasks

            tasks = get_tasks()
            if tasks:
                t = tasks[0]
                new_status = next((s for s in dict(COLUMNS) if s != t.status), t.status)
                mock_move.return_value = (replace(t, status=new_status), t.status)
            async with TestClient(example_app) as client:
                auth = await _login(client)
                result = await client.sse("/events", max_events=3, headers=auth)
        # Events use Fragment target as event name (e.g. column-backlog, board-stats)
        html_events = [e for e in result.events if e.data]
        assert len(html_events) >= 3
        for evt in html_events:
            assert "{{" not in evt.data
            assert "{%" not in evt.data

    async def test_sse_includes_oob_swaps(self, example_app) -> None:
        """SSE fragment events include hx-swap-oob for targeted updates."""
        with (
            patch("app.random_move") as mock_move,
            patch("app.asyncio.sleep", new_callable=AsyncMock),
        ):
            from dataclasses import replace

            from store import COLUMNS, get_tasks

            tasks = get_tasks()
            if tasks:
                t = tasks[0]
                new_status = next((s for s in dict(COLUMNS) if s != t.status), t.status)
                mock_move.return_value = (replace(t, status=new_status), t.status)
            async with TestClient(example_app) as client:
                auth = await _login(client)
                result = await client.sse("/events", max_events=3, headers=auth)
        oob_events = [e for e in result.events if e.data and "hx-swap-oob" in e.data]
        assert len(oob_events) >= 1
