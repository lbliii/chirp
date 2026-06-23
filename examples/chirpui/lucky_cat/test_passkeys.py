"""Passkey ceremony tests for Lucky Cat (#464)."""

from __future__ import annotations

import importlib

import pytest

from chirp.security.passkeys import _has_webauthn
from chirp.testing import TestClient
from tests.helpers.auth import csrf_post, extract_csrf_token, extract_session_cookie, login
from tests.helpers.passkeys_vectors import (
    AUTH_CREDENTIAL,
    REG_CREDENTIAL,
    TEST_PASSKEY_CONFIG,
    patch_fixed_ceremony,
    seeded_auth_passkey,
)

_SESSION_COOKIE = "chirp_session_lucky_cat"
_USERNAME = "neko"
_PASSWORD = "luckycat"

requires_webauthn = pytest.mark.skipif(
    not _has_webauthn(), reason="webauthn not installed (pip install chirp[passkeys])"
)


@pytest.fixture(autouse=True)
def _reset_passkeys(example_app):
    store = importlib.import_module("passkey_store")
    store.reset()
    yield
    store.reset()


@pytest.fixture
def passkey_config(monkeypatch):
    import passkey_config as pk_mod

    monkeypatch.setattr(pk_mod, "PASSKEY_CONFIG", TEST_PASSKEY_CONFIG)
    monkeypatch.setattr(pk_mod, "_ORIGIN", TEST_PASSKEY_CONFIG.origin)
    monkeypatch.setattr(pk_mod, "_RP_ID", TEST_PASSKEY_CONFIG.rp_id)
    monkeypatch.setattr(pk_mod, "config_for_request", lambda request: TEST_PASSKEY_CONFIG)
    return TEST_PASSKEY_CONFIG


async def _csrf_headers(client, *, cookie: str | None = None, via: str = "/login"):
    page = await client.get(
        via,
        headers={"Cookie": f"{_SESSION_COOKIE}={cookie}"} if cookie else {},
    )
    csrf = extract_csrf_token(page.text)
    current = extract_session_cookie(page, cookie_name=_SESSION_COOKIE) or cookie
    headers: dict[str, str] = {}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    if current:
        headers["Cookie"] = f"{_SESSION_COOKIE}={current}"
    return headers, current


@requires_webauthn
class TestLuckyCatPasskeys:
    @pytest.mark.issue(464)
    async def test_login_page_shows_passkey_button(self, example_app) -> None:
        async with TestClient(example_app) as client:
            html = (await client.get("/login")).text
            assert 'id="passkey-login"' in html

    @pytest.mark.issue(464)
    async def test_login_page_loads_passkey_handler_script(self, example_app) -> None:
        """Passkey UI uses an external script — inline handlers break under hx-boost CSP."""
        async with TestClient(example_app) as client:
            response = await client.get("/login")
            html = response.text
            assert 'src="/static/lucky-cat-passkeys.js"' in html
            assert "getElementById('passkey-login')" not in html

    @pytest.mark.issue(464)
    async def test_register_finish_persists_for_demo_user(
        self, example_app, passkey_config, monkeypatch
    ) -> None:
        patch_fixed_ceremony(monkeypatch)
        store = importlib.import_module("passkey_store")

        async with TestClient(example_app) as client:
            cookie = await login(
                client,
                username=_USERNAME,
                password=_PASSWORD,
                cookie_name=_SESSION_COOKIE,
            )
            _, cookie = await csrf_post(
                client,
                "/auth/passkey/register/begin",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                htmx=False,
            )
            headers, _ = await _csrf_headers(client, cookie=cookie, via="/settings/security")
            finish = await client.post(
                "/auth/passkey/register/finish",
                json=REG_CREDENTIAL,
                headers=headers,
            )
            assert finish.status == 200
            assert store.list_for_user(_USERNAME)

    @pytest.mark.issue(464)
    async def test_passkey_login_grants_gated_access(
        self, example_app, passkey_config, monkeypatch
    ) -> None:
        patch_fixed_ceremony(monkeypatch)
        store = importlib.import_module("passkey_store")
        row = seeded_auth_passkey(_USERNAME)
        store.seed(
            store.StoredPasskey(
                credential_id=row.credential_id,
                public_key=row.public_key,
                sign_count=row.sign_count,
                user_id=row.user_id,
            )
        )

        async with TestClient(example_app) as client:
            headers, _ = await _csrf_headers(client)
            begin = await client.post("/auth/passkey/login/begin", headers=headers)
            begin_cookie = extract_session_cookie(begin, cookie_name=_SESSION_COOKIE) or (
                headers.get("Cookie", "").split("=", 1)[-1] if headers.get("Cookie") else None
            )
            if begin_cookie:
                headers["Cookie"] = f"{_SESSION_COOKIE}={begin_cookie}"
            finish = await client.post(
                "/auth/passkey/login/finish",
                json={**AUTH_CREDENTIAL, "next": "/portfolio"},
                headers=headers,
            )
            assert finish.status == 200
            cookie = extract_session_cookie(finish, cookie_name=_SESSION_COOKIE)
            portfolio = await client.get(
                "/portfolio",
                headers={"Cookie": f"{_SESSION_COOKIE}={cookie}"},
            )
            assert portfolio.status == 200
