"""Tests for the auth example — login, protected routes, logout."""

from chirp.testing import TestClient


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    """Extract a Set-Cookie value from response headers."""
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


class TestPublicRoutes:
    """Unauthenticated access to public pages."""

    async def test_index_shows_sign_in_link(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Sign in" in response.text

    async def test_login_page_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/login")
            assert response.status == 200
            assert "username" in response.text.lower()

    async def test_dashboard_redirects_to_login(self, example_app) -> None:
        """Protected route redirects unauthenticated users to /login."""
        async with TestClient(example_app) as client:
            response = await client.get("/dashboard")
            assert response.status == 302
            location = ""
            for hname, hvalue in response.headers:
                if hname == "location":
                    location = hvalue
            assert "/login" in location


class TestLoginFlow:
    """Login, access protected pages, logout."""

    async def test_valid_credentials_redirect_to_dashboard(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/login",
                body=b"username=admin&password=password",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 302
            location = ""
            for hname, hvalue in response.headers:
                if hname == "location":
                    location = hvalue
            assert "/dashboard" in location

    async def test_invalid_credentials_show_error(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/login",
                body=b"username=admin&password=wrong",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert "Invalid" in response.text

    async def test_full_login_dashboard_logout(self, example_app) -> None:
        """Login → dashboard → logout → dashboard redirects again."""
        async with TestClient(example_app) as client:
            # Login
            r1 = await client.post(
                "/login",
                body=b"username=admin&password=password",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            cookie = _extract_cookie(r1)
            assert cookie is not None

            # Dashboard is now accessible
            r2 = await client.get(
                "/dashboard",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r2.status == 200
            assert "Admin" in r2.text

            # Logout
            r3 = await client.post(
                "/logout",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert r3.status == 302
            logout_cookie = _extract_cookie(r3)

            # Dashboard redirects again after logout
            r4 = await client.get(
                "/dashboard",
                headers={"Cookie": f"chirp_session={logout_cookie}"},
            )
            assert r4.status == 302
