"""Tests for the contacts shell example."""

from chirp.testing import TestClient, assert_hx_retarget, assert_hx_trigger

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


class TestContactsShell:
    async def test_contacts_page_renders_full_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts")
            assert response.status == 200
            assert "Contacts Shell" in response.text
            assert "New contact" in response.text
            assert 'id="page-content"' in response.text
            assert 'id="contacts-page"' in response.text

    async def test_boosted_contacts_page_renders_fragment_only(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/contacts",
                target="main",
                headers={"HX-Boosted": "true"},
            )
            assert response.status == 200
            assert 'id="contacts-page"' in response.text
            assert "chirpui-app-shell__sidebar" not in response.text

    async def test_add_validation_retargets_form_card(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts/create",
                body=b"name=&email=",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert_hx_retarget(response, "#contact-form-card")

    async def test_add_success_preserves_active_query(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts/create",
                body=b"name=Zara+Example&email=zara%40example.com&q=alice",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "Alice Johnson" in response.text
            assert "Zara Example" not in response.text
            assert "4 total" in response.text

    async def test_edit_route_opens_inline_editor(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts/1/edit?q=alice")
            assert response.status == 200
            assert 'id="contact-edit-1"' in response.text
            assert 'value="Alice Johnson"' in response.text

    async def test_save_validation_keeps_row_in_edit_mode(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts/1/save",
                body=b"name=&email=bad&q=alice",
                headers=_FORM_CT,
            )
            assert response.status == 422
            assert 'id="contact-edit-1"' in response.text
            assert "required" in response.text.lower()

    async def test_save_success_recomputes_filtered_view(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts/1/save",
                body=b"name=Betty+Jones&email=betty%40example.com&q=alice",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "No contacts match this query." in response.text
            assert "Alice Johnson" not in response.text
            assert "Betty Jones" not in response.text
            assert "3 total" in response.text

    async def test_delete_success_recomputes_filtered_view_and_triggers_feedback(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.delete("/contacts/1/delete?q=alice")
            assert response.status == 200
            assert_hx_trigger(response, "contactDeleted")
            assert "No contacts match this query." in response.text
            assert "Alice Johnson" not in response.text
            assert "2 total" in response.text

    def test_example_app_passes_contract_check(self, example_app) -> None:
        example_app.check()
