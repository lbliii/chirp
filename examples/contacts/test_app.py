"""Tests for the contacts example — htmx CRUD, validation, OOB, response headers."""

from chirp.testing import (
    TestClient,
    assert_fragment_contains,
    assert_fragment_not_contains,
    assert_hx_push_url,
    assert_hx_retarget,
    assert_hx_trigger,
    assert_is_fragment,
)

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


class TestContactList:
    """GET / returns the contact list as a full page or fragment."""

    async def test_index_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html>" in response.text
            assert "Contacts" in response.text
            assert "Alice Johnson" in response.text

    async def test_index_fragment(self, example_app) -> None:
        """Fragment request returns just the table, not the full page."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/")
            assert_is_fragment(response)
            assert_fragment_contains(response, "Alice Johnson")
            assert_fragment_not_contains(response, "<h1>")


class TestAddContact:
    """POST /contacts — add with validation and OOB count update."""

    async def test_add_valid(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts",
                body=b"name=Dave+Brown&email=dave%40example.com",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "Dave Brown" in response.text

    async def test_add_invalid_empty_name(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts",
                body=b"name=&email=test%40example.com",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_add_invalid_bad_email(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts",
                body=b"name=Test&email=not-an-email",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert "@" in response.text

    async def test_add_retargets_on_error(self, example_app) -> None:
        """ValidationError includes HX-Retarget to swap errors into the form."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts",
                body=b"name=&email=",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert_hx_retarget(response, "#form-section")

    async def test_add_updates_count_oob(self, example_app) -> None:
        """Successful add returns an OOB fragment to update the count badge."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts",
                body=b"name=Eve+White&email=eve%40example.com",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert 'hx-swap-oob' in response.text
            assert 'contact-count' in response.text


class TestEditContact:
    """GET /contacts/{id}/edit and PUT /contacts/{id}."""

    async def test_edit_form(self, example_app) -> None:
        """GET /contacts/1/edit returns the inline edit fragment."""
        async with TestClient(example_app) as client:
            response = await client.get("/contacts/1/edit")
            assert response.status == 200
            assert 'name="name"' in response.text
            assert "Alice Johnson" in response.text

    async def test_edit_pushes_url(self, example_app) -> None:
        """The edit fragment pushes a bookmarkable URL."""
        async with TestClient(example_app) as client:
            response = await client.get("/contacts/1/edit")
            assert_hx_push_url(response, "/contacts/1/edit")

    async def test_save_valid(self, example_app) -> None:
        """PUT /contacts/1 with valid data returns the updated row + OOB count."""
        async with TestClient(example_app) as client:
            response = await client.put(
                "/contacts/1",
                body=b"name=Alice+Updated&email=alice2%40example.com",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "Alice Updated" in response.text
            assert 'hx-swap-oob' in response.text

    async def test_save_invalid(self, example_app) -> None:
        """PUT /contacts/1 with bad data returns 422."""
        async with TestClient(example_app) as client:
            response = await client.put(
                "/contacts/1",
                body=b"name=&email=bad",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert "required" in response.text.lower()


class TestDeleteContact:
    """DELETE /contacts/{id} — removes contact and fires HX-Trigger."""

    async def test_delete(self, example_app) -> None:
        """Delete removes the contact from the table."""
        async with TestClient(example_app) as client:
            response = await client.delete("/contacts/1")
            assert response.status == 200
            assert_fragment_not_contains(response, "Alice Johnson")
            assert_fragment_contains(response, "Bob Smith")

    async def test_delete_fires_hx_trigger(self, example_app) -> None:
        """Delete response includes HX-Trigger: contactDeleted."""
        async with TestClient(example_app) as client:
            response = await client.delete("/contacts/1")
            assert_hx_trigger(response, "contactDeleted")


class TestSearchContacts:
    """GET /contacts/search?q= — filters contacts by name/email."""

    async def test_search_matches(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts/search?q=alice")
            assert response.status == 200
            assert "Alice Johnson" in response.text
            assert "Bob Smith" not in response.text

    async def test_search_empty(self, example_app) -> None:
        """No match returns the table with the empty-state message."""
        async with TestClient(example_app) as client:
            response = await client.get("/contacts/search?q=zzzzz")
            assert response.status == 200
            assert "No contacts found" in response.text
