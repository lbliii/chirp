"""Opt-in browser smoke for the blessed optimistic_apply primitive (#153).

The confirm/revert behavior is client-side JavaScript — a TestClient string
assert cannot see it. This drives real Chromium through the two flows and
asserts the adapter's own ``chirp:island:action`` event sequence (which is
timing-independent) plus the resulting DOM:

  * Like  -> apply:optimistic then confirm:confirmed; DOM ends count 43 + "liked".
  * Save (503, no swap) -> apply:optimistic then revert:reverted; DOM reverts to
    "Save (server will fail)" with the is-optimistic-error class (added ONLY by
    the revert branch) and the button re-enabled.

OPT-IN: ``pytest.importorskip("playwright")`` skips when Playwright is absent; a
missing Chromium binary skips (not fails) at launch. Install with::

    uv sync --group dev --group browser && uv run playwright install chromium
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright")

pytestmark = pytest.mark.issue(153)

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

_EXAMPLE_DIR = Path(__file__).parent
_REPO_ROOT = _EXAMPLE_DIR.parents[2]
_BOOT_TIMEOUT_S = 40.0
_ACTION_TIMEOUT_MS = 15_000

_RECORD = """
window.__optActions = [];
document.addEventListener('chirp:island:action', function (e) {
  window.__optActions.push((e.detail.action || '?') + ':' + (e.detail.status || '?'));
});
"""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def base_url() -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    runner = (
        "import sys; sys.argv = ['app.py']; import app as _a; "
        f"_a.app.run(host='127.0.0.1', port={port})"
    )
    env = {
        **os.environ,
        "CHIRP_ENV": "production",
        "CHIRP_SECRET_KEY": os.environ.get("CHIRP_SECRET_KEY", "browser-smoke-not-for-prod"),
        "PYTHONPATH": str(_REPO_ROOT / "src"),
    }
    cmd = ["uv", "run", "python", "-c", runner]  # uv is the mandated launcher
    proc = subprocess.Popen(  # noqa: S603
        cmd,
        cwd=str(_EXAMPLE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + _BOOT_TIMEOUT_S
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited early code={proc.returncode}")
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310, RUF100 -- fixed loopback URL
                    if resp.status == 200:
                        break
            except urllib.error.URLError, ConnectionError, OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("server did not come up")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        try:
            chromium = pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"Chromium not installed for Playwright: {exc}")
        try:
            yield chromium
        finally:
            chromium.close()


def test_optimistic_confirm_and_revert(base_url: str, browser) -> None:
    page = browser.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.add_init_script(_RECORD)
    try:
        page.goto(base_url, wait_until="load", timeout=_ACTION_TIMEOUT_MS)
        page.wait_for_function(
            "() => !!window.htmx && window.__chirpIslands === true", timeout=_ACTION_TIMEOUT_MS
        )

        # Like: optimistic apply -> confirmed by the authoritative swap.
        assert page.locator("#like-btn .like-count").inner_text() == "42"
        page.locator("#like-btn").click()
        page.wait_for_function(
            "() => window.__optActions.some(a => a.startsWith('confirm'))",
            timeout=_ACTION_TIMEOUT_MS,
        )
        like_actions = page.evaluate("() => window.__optActions.slice()")
        assert any(a == "apply:optimistic" for a in like_actions), like_actions
        assert any(a == "confirm:confirmed" for a in like_actions), like_actions
        page.wait_for_timeout(300)  # let htmx settle
        assert page.locator("#like-btn .like-count").inner_text() == "43"
        assert "liked" in (page.locator("#like-btn").get_attribute("class") or "")

        # Save: optimistic apply -> reverted (503 does not swap).
        page.evaluate("() => { window.__optActions = []; }")
        page.locator("#save-btn").click()
        page.wait_for_function(
            "() => window.__optActions.some(a => a.startsWith('revert'))",
            timeout=_ACTION_TIMEOUT_MS,
        )
        page.wait_for_timeout(300)
        save_actions = page.evaluate("() => window.__optActions.slice()")
        assert any(a == "apply:optimistic" for a in save_actions), save_actions
        assert any(a == "revert:reverted" for a in save_actions), save_actions
        save = page.locator("#save-btn")
        assert "Save (server will fail)" in save.inner_text()
        assert "Saving" not in save.inner_text()
        assert "is-optimistic-error" in (save.get_attribute("class") or "")
        assert save.get_attribute("disabled") is None

        assert not page_errors, f"page errors: {page_errors}"
    finally:
        page.close()
