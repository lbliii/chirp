"""Tests for the signup example — validation, CSRF, registration flow."""

from chirp.testing import TestClient

_FORM_CT = {"Content-Type": "application/x-www-form-urlencoded"}


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    """Extract a Set-Cookie value from response headers."""
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
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


def _build_signup_body(
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "securepass123",
    confirm: str = "securepass123",
    csrf_token: str = "",
) -> bytes:
    """Build URL-encoded signup form body."""
    from urllib.parse import urlencode

    return urlencode({
        "_csrf_token": csrf_token,
        "username": username,
        "email": email,
        "password": password,
        "confirm_password": confirm,
    }).encode()


class TestSignupPage:
    """GET /signup renders the registration form."""

    async def test_signup_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/signup")
            assert response.status == 200
            assert "Create an account" in response.text
            assert 'name="username"' in response.text

    async def test_signup_page_has_csrf_token(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/signup")
            assert '_csrf_token' in response.text

    async def test_index_redirects_to_signup(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 302


class TestValidation:
    """POST /signup — validation rules produce per-field errors."""

    async def test_empty_fields_required(self, example_app) -> None:
        """All empty fields produce 'required' errors."""
        async with TestClient(example_app) as client:
            # Get CSRF token first
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            response = await client.post(
                "/signup",
                body=_build_signup_body(
                    username="", email="", password="", confirm="",
                    csrf_token=token,
                ),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "required" in response.text.lower()

    async def test_username_too_short(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            response = await client.post(
                "/signup",
                body=_build_signup_body(username="ab", csrf_token=token),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "at least 3" in response.text.lower()

    async def test_invalid_email(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            response = await client.post(
                "/signup",
                body=_build_signup_body(email="not-an-email", csrf_token=token),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "valid email" in response.text.lower()

    async def test_password_too_short(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            response = await client.post(
                "/signup",
                body=_build_signup_body(password="short", confirm="short", csrf_token=token),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "at least 8" in response.text.lower()

    async def test_passwords_dont_match(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            response = await client.post(
                "/signup",
                body=_build_signup_body(
                    password="securepass123", confirm="different123",
                    csrf_token=token,
                ),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "do not match" in response.text.lower()

    async def test_invalid_username_chars(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            response = await client.post(
                "/signup",
                body=_build_signup_body(username="bad user!", csrf_token=token),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 422
            assert "underscores" in response.text.lower()


class TestCSRF:
    """CSRF protection blocks requests without a valid token."""

    async def test_missing_csrf_token_rejected(self, example_app) -> None:
        """POST without CSRF token gets 403."""
        async with TestClient(example_app) as client:
            page = await client.get("/signup")
            cookie = _extract_cookie(page)

            response = await client.post(
                "/signup",
                body=b"username=test&email=t%40t.com&password=12345678&confirm_password=12345678",
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 403


class TestRegistrationFlow:
    """Full registration → welcome page flow."""

    async def test_successful_signup_redirects(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            response = await client.post(
                "/signup",
                body=_build_signup_body(csrf_token=token),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 302
            location = ""
            for hname, hvalue in response.headers:
                if hname == "location":
                    location = hvalue
            assert "/welcome" in location

    async def test_welcome_page_shows_username(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Register
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            r1 = await client.post(
                "/signup",
                body=_build_signup_body(username="janedoe", csrf_token=token),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )
            new_cookie = _extract_cookie(r1) or cookie

            # Visit welcome page
            r2 = await client.get(
                "/welcome",
                headers={"Cookie": f"chirp_session={new_cookie}"},
            )
            assert r2.status == 200
            assert "janedoe" in r2.text

    async def test_duplicate_username_rejected(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Register first user
            page = await client.get("/signup")
            cookie = _extract_cookie(page)
            token = _extract_csrf_token(page)

            await client.post(
                "/signup",
                body=_build_signup_body(username="taken_user", csrf_token=token),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie}"},
            )

            # Get a fresh page + token for second attempt
            page2 = await client.get("/signup")
            cookie2 = _extract_cookie(page2)
            token2 = _extract_csrf_token(page2)

            response = await client.post(
                "/signup",
                body=_build_signup_body(username="taken_user", csrf_token=token2),
                headers={**_FORM_CT, "Cookie": f"chirp_session={cookie2}"},
            )
            assert response.status == 422
            assert "already taken" in response.text.lower()
