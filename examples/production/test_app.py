"""Tests for the production example."""

from urllib.parse import urlencode

from chirp.testing import TestClient

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    """Extract a Set-Cookie value from response headers."""
    for hname, hvalue in response.headers:
        if hname.lower() == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


def _extract_csrf_token(response) -> str:
    """Extract the CSRF token from a hidden input in the response body."""
    text = response.text
    marker = 'name="_csrf_token" value="'
    start = text.find(marker)
    assert start != -1, "CSRF token not found in response"
    start += len(marker)
    end = text.find('"', start)
    return text[start:end]


class TestProductionApp:
    """Verify production example routes and security headers."""

    async def test_index_returns_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "text/html" in response.content_type
            assert "Contact us" in response.text
            assert "csrf" in response.text.lower()

    async def test_security_headers_on_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            headers = {k.lower(): v for k, v in response.headers}
            assert "x-frame-options" in headers
            assert "x-content-type-options" in headers
            assert "referrer-policy" in headers

    async def test_contact_post_without_csrf_fails(self, example_app) -> None:
        async with TestClient(example_app) as client:
            await client.get("/")
            body = urlencode(
                {
                    "name": "Alice",
                    "email": "a@b.com",
                    "message": "Hi",
                }
            ).encode()
            response = await client.post("/contact", body=body, headers=_FORM_CT)
            assert response.status == 403

    async def test_contact_post_with_csrf_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)
            body = urlencode(
                {
                    "_csrf_token": token,
                    "name": "Alice",
                    "email": "a@b.com",
                    "message": "Hello",
                }
            ).encode()
            response = await client.post(
                "/contact",
                body=body,
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 302
            assert "/thank-you" in response.header("location", "")

    async def test_thank_you_shows_name(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)
            body = urlencode(
                {
                    "_csrf_token": token,
                    "name": "Bob",
                    "email": "bob@example.com",
                    "message": "Hi",
                }
            ).encode()
            post_resp = await client.post(
                "/contact",
                body=body,
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            new_cookie = _extract_cookie(post_resp) or cookie
            response = await client.get(
                "/thank-you",
                headers={"Cookie": f"chirp_session={new_cookie}"},
            )
            assert response.status == 200
            assert "Thank you" in response.text
            assert "Bob" in response.text
