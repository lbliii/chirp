"""Tests for the sortable_reorder example."""

from chirp.testing import TestClient

from tests.helpers.auth import extract_csrf_token, extract_session_cookie

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


def _auth_headers(client_response) -> tuple[dict[str, str], str | None]:
    """Build headers with session cookie and CSRF for POST requests."""
    cookie = extract_session_cookie(client_response, cookie_name="chirp_session_sortable_reorder")
    csrf = extract_csrf_token(client_response.text)
    headers = dict(_FORM_CT)
    if cookie:
        headers["Cookie"] = f"chirp_session_sortable_reorder={cookie}"
    return headers, csrf


class TestSortableReorder:
    async def test_index_renders_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Sortable Reorder" in response.text
            assert "Reorder list" in response.text
            assert "First" in response.text
            assert "chirpui-sortable" in response.text
            assert 'id="item-list"' in response.text

    async def test_add_item_updates_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r0 = await client.get("/")
            headers, csrf = _auth_headers(r0)
            assert csrf is not None
            body = f"name=NewItem&_csrf_token={csrf}"
            response = await client.post("/items", body=body.encode(), headers=headers)
            assert response.status == 200
            assert "NewItem" in response.text
            assert "First" in response.text

    async def test_reorder_updates_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r0 = await client.get("/")
            headers, csrf = _auth_headers(r0)
            assert csrf is not None
            # Move item from index 0 to index 2 (First -> Third position)
            body = f"from_idx=0&to_idx=2&_csrf_token={csrf}"
            response = await client.post("/reorder", body=body.encode(), headers=headers)
            assert response.status == 200
            # After reorder: Second, Third, First, Fourth, Fifth
            text = response.text
            assert "First" in text
            assert "Second" in text
            # First should appear after Second and Third in the new order
            second_pos = text.find("Second")
            first_pos = text.find("First")
            assert second_pos < first_pos

    def test_example_app_passes_contract_check(self, example_app) -> None:
        example_app.check()
