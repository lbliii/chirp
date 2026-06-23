"""Opt-in browser e2e for passkeys_minimal with a virtual authenticator (#465).

Drives real ``navigator.credentials`` through ``window.chirp.passkeys`` using
Chrome DevTools Protocol WebAuthn commands. Skips when Playwright or Chromium is
absent.

Uses ``localhost`` (not ``127.0.0.1``) for ``PasskeyConfig`` — Chromium rejects
``127.0.0.1`` as an rp_id for ``http://localhost:*`` origins.

Install::

    uv sync --group dev --group browser && uv run playwright install chromium
    uv run --with 'webauthn>=2.8,<3' pytest examples/standalone/passkeys_minimal/test_browser_smoke.py -m passkeys_e2e
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright")

pytestmark = [pytest.mark.issue(465), pytest.mark.passkeys_e2e]

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

_EXAMPLE_DIR = Path(__file__).parent
_REPO_ROOT = _EXAMPLE_DIR.parents[2]
_BOOT_TIMEOUT_S = 40.0
_ACTION_TIMEOUT_MS = 20_000

_REGISTER_JS = """
async () => {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const begin = await fetch('/auth/passkey/register/begin', {
    method: 'POST',
    headers: {'X-CSRF-Token': csrf},
  });
  const opts = await begin.json();
  const credential = await window.chirp.passkeys.register(opts);
  const finish = await fetch('/auth/passkey/register/finish', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: JSON.stringify(credential),
  });
  return finish.status;
}
"""

_AUTH_JS = """
async (nextUrl) => {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const begin = await fetch('/auth/passkey/login/begin', {
    method: 'POST',
    headers: {'X-CSRF-Token': csrf},
  });
  const opts = await begin.json();
  const credential = await window.chirp.passkeys.authenticate(opts);
  const finish = await fetch('/auth/passkey/login/finish', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: JSON.stringify(Object.assign({}, credential, {next: nextUrl})),
  });
  const result = await finish.json();
  if (!finish.ok || !result.ok) throw new Error(result.error || 'finish failed');
  window.location = result.redirect || nextUrl;
}
"""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _extract_csrf(html: str) -> str | None:
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None


def _session_cookie(set_cookie: str | None) -> str | None:
    if not set_cookie or not set_cookie.startswith("chirp_session="):
        return None
    return set_cookie.split(";")[0].partition("=")[2]


@pytest.fixture
def base_url() -> Iterator[str]:
    port = _free_port()
    url = f"http://localhost:{port}"
    runner = (
        "import sys; from dataclasses import replace; sys.argv = ['app.py']; import app as _a; "
        f"_a.config = replace(_a.config, workers=1); "
        f"_a.app.run(host='127.0.0.1', port={port})"
    )
    env = {
        **os.environ,
        "CHIRP_ENV": "development",
        "CHIRP_SECRET_KEY": os.environ.get("CHIRP_SECRET_KEY", "browser-smoke-not-for-prod"),
        "PASSKEY_ORIGIN": url,
        "PASSKEY_RP_ID": "localhost",
        "PYTHONPATH": str(_REPO_ROOT / "src"),
    }
    cmd = [
        "uv",
        "run",
        "--with",
        "webauthn>=2.8,<3",
        "python",
        "-c",
        runner,
    ]
    proc = subprocess.Popen(  # noqa: S603
        cmd,
        cwd=str(_EXAMPLE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + _BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out = (proc.stdout.read() if proc.stdout else b"").decode()
            pytest.fail(f"passkeys_minimal failed to boot:\n{out}")
        try:
            with urllib.request.urlopen(f"{url}/login", timeout=1) as resp:  # noqa: S310
                if resp.status == 200:
                    break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.15)
    else:
        proc.kill()
        pytest.fail("Timed out waiting for passkeys_minimal to boot")
    try:
        yield url
    finally:
        proc.kill()
        proc.wait(timeout=5)


def _enable_virtual_authenticator(page) -> None:
    client = page.context.new_cdp_session(page)
    client.send("WebAuthn.enable")
    client.send(
        "WebAuthn.addVirtualAuthenticator",
        {
            "options": {
                "protocol": "ctap2",
                "transport": "internal",
                "hasResidentKey": True,
                "hasUserVerification": True,
                "isUserVerified": True,
                "automaticPresenceSimulation": True,
            }
        },
    )


def _seed_session(context, base_url: str) -> None:
    """Password-login via API so the browser starts with an authenticated session."""
    login_get = context.request.get(f"{base_url}/login")
    assert login_get.ok
    csrf = _extract_csrf(login_get.text())
    cookie = _session_cookie(login_get.headers.get("set-cookie"))
    assert csrf and cookie
    headers = {"X-CSRF-Token": csrf, "Cookie": f"chirp_session={cookie}"}
    login_post = context.request.post(
        f"{base_url}/login",
        form={"username": "admin", "password": "password", "_csrf_token": csrf},
        headers=headers,
    )
    assert login_post.ok and login_post.url.endswith("/dashboard")
    authed = _session_cookie(login_post.headers.get("set-cookie")) or cookie
    context.add_cookies(
        [
            {
                "name": "chirp_session",
                "value": authed,
                "url": base_url,
            }
        ]
    )


def test_passkey_register_and_sign_in(base_url: str) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            _seed_session(context, base_url)
            page = context.new_page()
            page.set_default_timeout(_ACTION_TIMEOUT_MS)
            _enable_virtual_authenticator(page)

            page.goto(f"{base_url}/passkeys")
            assert page.evaluate(_REGISTER_JS) == 200
            page.reload()
            assert page.locator("#passkey-list li").count() >= 1

            context.clear_cookies()
            page.goto(f"{base_url}/login")
            page.evaluate(_AUTH_JS, "/dashboard")
            page.wait_for_url(f"{base_url}/dashboard")
            assert "Welcome" in page.content()

            browser.close()
    except PlaywrightError as exc:
        pytest.skip(f"Playwright/Chromium unavailable: {exc}")
