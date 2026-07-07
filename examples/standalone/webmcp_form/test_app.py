"""Executable proof for the declarative WebMCP form example."""

import pytest

from chirp.contracts import check_hypermedia_surface
from chirp.testing import TestClient
from tests.helpers.auth import csrf_post

pytestmark = [pytest.mark.issue(574), pytest.mark.issue(575)]


async def test_form_is_agent_visible_and_keeps_native_submission(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.get("/")

    assert 'method="post" action="/tasks"' in response.text.replace("\n", " ")
    assert 'toolname="tasks.create"' in response.text
    assert 'name="title" required' in response.text
    assert "document.modelContext" not in response.text


async def test_same_handler_validates_and_redirects(example_app) -> None:
    async with TestClient(example_app) as client:
        invalid, cookie = await csrf_post(
            client,
            "/tasks",
            cookie=None,
            data={"priority": "2"},
            htmx=False,
        )
        valid, cookie = await csrf_post(
            client,
            "/tasks",
            cookie=cookie,
            data={"title": "Ship", "priority": "1"},
            htmx=False,
        )
        htmx, _ = await csrf_post(
            client,
            "/tasks",
            cookie=cookie,
            data={"title": "Fragment", "priority": "3"},
            extra_headers={"HX-Target": "task-form"},
        )

    assert invalid.status == 422
    assert "title is required" in invalid.text
    assert valid.status == 303
    assert valid.header("Location") == "/"
    assert htmx.status == 200
    assert htmx.header("HX-Redirect") == "/"


def test_example_contracts_are_clean(example_app) -> None:
    result = check_hypermedia_surface(example_app)
    assert result.errors == []
