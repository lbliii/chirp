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
            assert "Recipe Builder" in response.text
            assert "Preheat oven" in response.text
            assert "chirpui-sortable" in response.text
            assert 'id="recipe-content"' in response.text

    async def test_add_step_updates_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r0 = await client.get("/")
            headers, csrf = _auth_headers(r0)
            assert csrf is not None
            body = f"instruction=Let+it+cool&duration=10+min&note=&_csrf_token={csrf}"
            response = await client.post("/steps", body=body.encode(), headers=headers)
            assert response.status == 200
            assert "Let it cool" in response.text
            assert "Preheat oven" in response.text

    async def test_reorder_updates_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r0 = await client.get("/")
            headers, csrf = _auth_headers(r0)
            assert csrf is not None
            body = f"from_idx=0&to_idx=2&_csrf_token={csrf}"
            response = await client.post("/reorder", body=body.encode(), headers=headers)
            assert response.status == 200
            text = response.text
            assert "Preheat oven" in text
            assert "Dice onions" in text

    async def test_delete_step(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r0 = await client.get("/")
            headers, csrf = _auth_headers(r0)
            assert csrf is not None
            body = f"step_id=1&_csrf_token={csrf}"
            response = await client.post("/steps/delete", body=body.encode(), headers=headers)
            assert response.status == 200
            assert "Preheat oven to 375" not in response.text

    def test_example_app_passes_contract_check(self, example_app) -> None:
        example_app.check()
