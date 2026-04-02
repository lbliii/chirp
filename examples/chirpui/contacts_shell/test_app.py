"""Tests for the contacts shell example."""

from chirp.testing import TestClient, assert_hx_trigger

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


class TestContactsShell:
    async def test_contacts_page_renders_full_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts")
            assert response.status == 200
            assert "Team Directory" in response.text
            assert "New contact" in response.text
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
            assert 'id="page-root"' in response.text
            assert "chirpui-app-shell__sidebar" not in response.text

    async def test_add_success(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts",
                body=b"_action=create&name=Zara+Example&email=zara%40example.com&q=&group_filter=",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert "Zara Example" in response.text

    async def test_group_filter(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts?group=Design")
            assert response.status == 200
            assert "Carol Williams" in response.text
            assert "Alice Chen" not in response.text

    async def test_edit_route_opens_inline_editor(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts/1/edit?q=alice")
            assert response.status == 200
            assert 'id="contact-edit-1"' in response.text
            assert 'value="Alice Chen"' in response.text

    async def test_save_success(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts/1",
                body=b"_action=save&name=Betty+Jones&email=betty%40example.com&q=&group=Engineering",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert_hx_trigger(response, "contactSaved")
            assert "Betty Jones" in response.text

    async def test_delete_success_triggers_feedback(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/contacts/1",
                body=b"_action=delete&q=",
                headers=_FORM_CT,
            )
            assert response.status == 200
            assert_hx_trigger(response, "contactDeleted")
            assert "Alice Chen" not in response.text

    async def test_contact_detail_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/contacts/1")
            assert response.status == 200
            assert "Alice Chen" in response.text
            assert "Contact Details" in response.text

    def test_example_app_passes_contract_check(self, example_app) -> None:
        example_app.check()
