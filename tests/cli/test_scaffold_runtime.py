"""End-to-end smoke of generated v2 projects via TestClient.

Scaffolds a project, then runs an HTTP flow in a subprocess:

- GET /                         → 200
- POST /login happy path        → 302 to /dashboard
- POST /login wrong password    → 200 with "Invalid"
- GET /dashboard unauthenticated → 302 to /login
- GET /dashboard authenticated   → 200 with "Admin"
- POST /dashboard/refresh (v2+chirpui only) → 200 with OOB counter + stamp

Complementary to ``test_scaffold_contracts.py`` (which only exercises freeze).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import run_and_parse, scaffold

_RUNTIME_CODE = r"""
import asyncio, json, re, sys

sys.path.insert(0, ".")
from app import app
from chirp.testing import TestClient


_CSRF_RE = re.compile(r'name="_csrf_token" value="([^"]+)"')


def _extract_csrf(html: str) -> str | None:
    m = _CSRF_RE.search(html)
    return m.group(1) if m else None


def _session_cookie(response) -> str | None:
    for name, value in response.headers:
        if name == "set-cookie" and value.startswith("chirp_session="):
            return value.split(";")[0].partition("=")[2]
    return None


async def main():
    out = {"steps": {}}
    async with TestClient(app) as client:
        # 1. GET /
        r = await client.get("/")
        out["steps"]["index"] = {"status": r.status, "has_welcome": "Welcome" in r.text or "Dashboard" in r.text}

        # 2. GET /login — grab CSRF + session cookie
        r = await client.get("/login")
        csrf = _extract_csrf(r.text)
        cookie = _session_cookie(r)
        out["steps"]["login_get"] = {"status": r.status, "csrf": bool(csrf), "cookie": bool(cookie)}

        # 3. POST /login with bad password
        r = await client.post(
            "/login",
            body=f"username=admin&password=wrong&_csrf_token={csrf}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={cookie}",
            },
        )
        out["steps"]["login_bad"] = {"status": r.status, "has_invalid": "Invalid" in r.text}

        # 4. POST /login with good password → expect redirect
        r = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={csrf}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={cookie}",
            },
        )
        loc = ""
        for n, v in r.headers:
            if n == "location":
                loc = v
        auth_cookie = _session_cookie(r) or cookie
        out["steps"]["login_good"] = {"status": r.status, "location": loc}

        # 5. GET /dashboard unauthenticated (no cookie)
        r = await client.get("/dashboard")
        anon_loc = ""
        for n, v in r.headers:
            if n == "location":
                anon_loc = v
        out["steps"]["dashboard_anon"] = {"status": r.status, "location": anon_loc}

        # 6. GET /dashboard authenticated
        r = await client.get("/dashboard", headers={"Cookie": f"chirp_session={auth_cookie}"})
        out["steps"]["dashboard_auth"] = {"status": r.status, "has_admin": "Admin" in r.text}

        # 7. POST /dashboard/refresh — OOB two-target swap (v2+chirpui only)
        csrf2 = _extract_csrf(r.text)
        refresh_cookie = _session_cookie(r) or auth_cookie
        r = await client.post(
            "/dashboard/refresh",
            body=f"_csrf_token={csrf2}".encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={refresh_cookie}",
            },
        )
        out["steps"]["refresh"] = {
            "status": r.status,
            "has_count": "Count:" in r.text,
            "has_oob_stamp": 'id="refresh-stamp"' in r.text and 'hx-swap-oob' in r.text,
        }

    print(json.dumps(out))


asyncio.run(main())
"""


@pytest.mark.parametrize("mode", ["v2", "v2_plain"])
def test_v2_scaffold_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode=mode)
    result = run_and_parse(project, _RUNTIME_CODE)

    assert result.returncode == 0, (
        f"Scaffold '{mode}' runtime subprocess failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    steps = result.payload.get("steps", {})

    # 1. index
    assert steps["index"]["status"] == 200

    # 2. login GET
    assert steps["login_get"]["status"] == 200
    assert steps["login_get"]["csrf"] is True
    assert steps["login_get"]["cookie"] is True

    # 3. login with bad password → re-rendered form (Sprint 3 invariant)
    assert steps["login_bad"]["status"] == 200
    assert steps["login_bad"]["has_invalid"] is True

    # 4. login happy path → redirect
    assert steps["login_good"]["status"] == 302
    assert "/dashboard" in steps["login_good"]["location"]

    # 5. dashboard unauthenticated → redirect to login
    assert steps["dashboard_anon"]["status"] == 302
    assert "/login" in steps["dashboard_anon"]["location"]

    # 6. dashboard authenticated → 200 + user name visible
    assert steps["dashboard_auth"]["status"] == 200
    assert steps["dashboard_auth"]["has_admin"] is True

    # 7. OOB demo — only wired in chirpui variant; plain v2 returns 404
    refresh = steps["refresh"]
    if mode == "v2":
        assert refresh["status"] == 200
        assert refresh["has_count"] is True
        assert refresh["has_oob_stamp"] is True
    else:
        assert refresh["status"] == 404
