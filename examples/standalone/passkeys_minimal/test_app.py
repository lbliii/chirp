"""Tests for passkeys_minimal — password auth + WebAuthn ceremony routes."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

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

requires_webauthn = pytest.mark.skipif(
    not _has_webauthn(), reason="webauthn not installed (pip install chirp[passkeys])"
)


@pytest.fixture(autouse=True)
def _reset_store(example_app):
    store = importlib.import_module("credential_store")
    store.reset()
    yield
    store.reset()


@pytest.fixture
def passkey_config(monkeypatch, request):
    module_name = f"example_{Path(request.path).parent.name}"
    mod = sys.modules[module_name]
    monkeypatch.setattr(mod, "PK", TEST_PASSKEY_CONFIG)
    return TEST_PASSKEY_CONFIG


async def _csrf_headers(client, *, cookie: str | None = None, via: str = "/login"):
    page = await client.get(via, headers={"Cookie": f"chirp_session={cookie}"} if cookie else {})
    csrf = extract_csrf_token(page.text)
    current = extract_session_cookie(page) or cookie
    headers: dict[str, str] = {}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    if current:
        headers["Cookie"] = f"chirp_session={current}"
    return headers, current


class TestPasswordAuth:
    @pytest.mark.issue(463)
    async def test_password_login_still_works(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await login(client, username="admin", password="password")
            assert cookie
            dash = await client.get("/dashboard", headers={"Cookie": f"chirp_session={cookie}"})
            assert dash.status == 200
            assert "Admin" in dash.text


@requires_webauthn
class TestPasskeyCeremony:
    @pytest.mark.issue(463)
    async def test_register_begin_returns_options(self, example_app, passkey_config) -> None:
        async with TestClient(example_app) as client:
            cookie = await login(client, username="admin", password="password")
            response, _ = await csrf_post(
                client,
                "/auth/passkey/register/begin",
                cookie=cookie,
                htmx=False,
            )
            assert response.status == 200
            body = json.loads(response.text)
            assert body["challenge"]
            assert body["rp"]["id"] == "localhost"

    @pytest.mark.issue(463)
    async def test_register_finish_persists_credential(
        self, example_app, passkey_config, monkeypatch
    ) -> None:
        patch_fixed_ceremony(monkeypatch)
        store = importlib.import_module("credential_store")

        async with TestClient(example_app) as client:
            cookie = await login(client, username="admin", password="password")
            _, cookie = await csrf_post(
                client,
                "/auth/passkey/register/begin",
                cookie=cookie,
                htmx=False,
            )
            headers, cookie = await _csrf_headers(client, cookie=cookie)
            finish = await client.post(
                "/auth/passkey/register/finish",
                json=REG_CREDENTIAL,
                headers=headers,
            )
            assert finish.status == 200
            assert json.loads(finish.text)["ok"] is True
            assert store.list_for_user("admin")

    @pytest.mark.issue(463)
    async def test_authenticate_finish_logs_in(
        self, example_app, passkey_config, monkeypatch
    ) -> None:
        patch_fixed_ceremony(monkeypatch)
        store = importlib.import_module("credential_store")
        row = seeded_auth_passkey("admin")
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
            begin_cookie = extract_session_cookie(begin) or (
                headers.get("Cookie", "").split("=", 1)[-1] if headers.get("Cookie") else None
            )
            if begin_cookie:
                headers["Cookie"] = f"chirp_session={begin_cookie}"
            finish = await client.post(
                "/auth/passkey/login/finish",
                json={**AUTH_CREDENTIAL, "next": "/dashboard"},
                headers=headers,
            )
            assert finish.status == 200
            assert json.loads(finish.text)["redirect"] == "/dashboard"
            authed = extract_session_cookie(finish)
            dash = await client.get("/dashboard", headers={"Cookie": f"chirp_session={authed}"})
            assert dash.status == 200
