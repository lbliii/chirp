"""Auth flow tests for testv2."""

from chirp.testing import TestClient


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{name}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


async def test_index_public():
    from app import app
    async with TestClient(app) as client:
        response = await client.get("/")
        assert response.status == 200


async def test_dashboard_requires_login():
    from app import app
    async with TestClient(app) as client:
        response = await client.get("/dashboard")
        assert response.status == 302
        assert "/login" in response.header("location", "")


async def test_login_success():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie = _extract_cookie(r1)
        assert csrf and cookie
        r = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={csrf}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={cookie}",
            },
        )
        assert r.status == 302
        assert "/dashboard" in r.header("location", "")


async def test_login_failure():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie = _extract_cookie(r1)
        assert csrf and cookie
        r = await client.post(
            "/login",
            body=f"username=admin&password=wrong&_csrf_token={csrf}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={cookie}",
            },
        )
        assert r.status == 302
        assert "error=1" in r.header("location", "")


async def test_dashboard_authenticated():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie1 = _extract_cookie(r1)
        assert csrf and cookie1
        r2 = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={csrf}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={cookie1}",
            },
        )
        cookie = _extract_cookie(r2)
        assert cookie
        r3 = await client.get("/dashboard", headers={"Cookie": f"chirp_session={cookie}"})
        assert r3.status == 200
        assert "Admin" in r3.text


async def test_logout():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie1 = _extract_cookie(r1)
        assert csrf and cookie1
        r2 = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={csrf}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={cookie1}",
            },
        )
        cookie = _extract_cookie(r2)
        assert cookie
        r_dash = await client.get("/dashboard", headers={"Cookie": f"chirp_session={cookie}"})
        csrf2 = _extract_csrf_token(r_dash.text)
        cookie_dash = _extract_cookie(r_dash) or cookie
        r3 = await client.post(
            "/logout",
            body=f"_csrf_token={csrf2}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={cookie_dash}",
            },
        )
        assert r3.status == 302
        r4 = await client.get("/dashboard", headers={"Cookie": _extract_cookie(r3) or ""})
        assert r4.status == 302


async def test_csrf_required():
    from app import app
    async with TestClient(app) as client:
        r = await client.post(
            "/login",
            body=b"username=admin&password=password",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status == 403


def _extract_csrf_token(html: str) -> str | None:
    import re
    m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None
