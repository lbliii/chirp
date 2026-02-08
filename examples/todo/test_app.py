"""Tests for the todo example — htmx fragment rendering."""

from chirp.testing import (
    TestClient,
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_is_fragment,
)


class TestTodoFullPage:
    """GET / returns a full HTML page."""

    async def test_index_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html>" in response.text
            assert "<h1>Todos</h1>" in response.text
            assert '<ul id="todo-list">' in response.text

    async def test_index_fragment(self, example_app) -> None:
        """HX-Request header triggers fragment response (just the list)."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/")
            assert_is_fragment(response)
            assert_fragment_contains(response, '<ul id="todo-list">')
            assert_fragment_not_contains(response, "<h1>Todos</h1>")


class TestTodoOperations:
    """Add, toggle, and delete todos — each returns a fragment."""

    async def test_add_todo(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/todos",
                body=b"text=Buy+milk",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert_is_fragment(response)
            assert_fragment_contains(response, "Buy milk")

    async def test_add_and_toggle(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Add a todo
            await client.post(
                "/todos",
                body=b"text=Write+tests",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            # Toggle it — id should be 1 (first todo)
            response = await client.post("/todos/1/toggle")
            assert_is_fragment(response)
            assert_fragment_contains(response, "done")

            # Toggle again — should revert
            response = await client.post("/todos/1/toggle")
            assert_is_fragment(response)
            assert_fragment_contains(response, "todo")

    async def test_add_and_delete(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Add two todos
            await client.post(
                "/todos",
                body=b"text=First",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            await client.post(
                "/todos",
                body=b"text=Second",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            # Delete the first
            response = await client.delete("/todos/1")
            assert_is_fragment(response)
            assert_fragment_not_contains(response, "First")
            assert_fragment_contains(response, "Second")

    async def test_empty_text_returns_422(self, example_app) -> None:
        """Empty text triggers a ValidationError — 422 with error message."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/todos",
                body=b"text=",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_validation_error_still_renders_list(self, example_app) -> None:
        """A validation error still renders existing todos in the fragment."""
        async with TestClient(example_app) as client:
            # Add a valid todo first
            await client.post(
                "/todos",
                body=b"text=Existing+item",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            # Submit empty — should get 422 but still see the existing todo
            response = await client.post(
                "/todos",
                body=b"text=",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 422
            assert_fragment_contains(response, "Existing item")

    async def test_isolation_between_tests(self, example_app) -> None:
        """Each test gets a fresh app with an empty todo list."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "<li>" not in response.text
