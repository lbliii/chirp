"""No-JS floor proof — full CRUD with JavaScript disabled.

Every request here is a *plain* browser request: no ``HX-Request`` header is
ever sent, so htmx is effectively off. The point is to prove the progressive-
enhancement floor holds:

- GET renders the server-rendered list + create form.
- A valid create/edit/delete POST returns ``303`` and the followed redirect
  reflects the change (POST/redirect/GET).
- An invalid create/edit POST returns ``422`` with the re-rendered form HTML
  containing the inline error message.

The TestClient does not follow redirects automatically, so we read the
``Location`` header and issue the follow-up GET ourselves — exactly what a
browser with JS disabled does.
"""

from chirp.testing import TestClient

FORM_HEADERS = {"content-type": "application/x-www-form-urlencoded"}


class TestNoJsRenders:
    """GET serves a complete server-rendered page without any JS."""

    async def test_get_renders_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Buy milk" in response.text
            assert "Ship the floor demo" in response.text

    async def test_get_includes_plain_post_forms(self, example_app) -> None:
        """The mutation surface is plain ``<form method="post">`` — no hx-* needed."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert 'method="post"' in response.text
            assert "/notes" in response.text  # create form action
            assert "/delete" in response.text  # per-row delete form action
            assert "/edit" in response.text  # per-row edit form action


class TestNoJsCreate:
    """Plain POST create -> 303 redirect, then the list shows the new note."""

    async def test_valid_create_redirects_303(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/notes",
                body=b"title=Walk+the+dog&body=Around+the+block",
                headers=FORM_HEADERS,
            )
            assert response.status == 303
            assert response.header("location", "") == "/"

    async def test_valid_create_followed_redirect_shows_note(self, example_app) -> None:
        async with TestClient(example_app) as client:
            create = await client.post(
                "/notes",
                body=b"title=Walk+the+dog&body=Around+the+block",
                headers=FORM_HEADERS,
            )
            assert create.status == 303
            # Follow the redirect like a browser would.
            listed = await client.get(create.header("location", "/"))
            assert listed.status == 200
            assert "Walk the dog" in listed.text

    async def test_invalid_create_returns_422_with_error(self, example_app) -> None:
        """Empty title -> 422 + re-rendered create form carrying the error."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/notes",
                body=b"title=&body=no+title",
                headers=FORM_HEADERS,
            )
            assert response.status == 422
            assert "This field is required" in response.text
            # The rejected body value is echoed back into the form.
            assert "no title" in response.text

    async def test_invalid_create_does_not_persist(self, example_app) -> None:
        async with TestClient(example_app) as client:
            await client.post(
                "/notes",
                body=b"title=ab",  # below min_length(3)
                headers=FORM_HEADERS,
            )
            listed = await client.get("/")
            assert "Must be at least 3 characters" not in listed.text
            assert ">ab<" not in listed.text


class TestNoJsEdit:
    """Plain POST edit -> 303 redirect, then the change is reflected."""

    async def test_valid_edit_redirects_and_updates(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/notes/1/edit",
                body=b"title=Buy+oat+milk&body=Barista+blend",
                headers=FORM_HEADERS,
            )
            assert response.status == 303
            listed = await client.get(response.header("location", "/"))
            assert "Buy oat milk" in listed.text
            assert "Buy milk" not in listed.text

    async def test_invalid_edit_returns_422_with_error(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/notes/1/edit",
                body=b"title=&body=oops",
                headers=FORM_HEADERS,
            )
            assert response.status == 422
            assert "This field is required" in response.text


class TestNoJsDelete:
    """Plain POST delete -> 303 redirect, then the note is gone."""

    async def test_valid_delete_redirects_and_removes(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/notes/1/delete", headers=FORM_HEADERS)
            assert response.status == 303
            listed = await client.get(response.header("location", "/"))
            assert "Buy milk" not in listed.text
            # Sibling note is untouched.
            assert "Ship the floor demo" in listed.text
