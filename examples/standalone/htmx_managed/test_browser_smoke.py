"""Real-browser regression proof for the verified htmx 2.0.10 baseline (#543)."""

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
pytestmark = pytest.mark.issue(543)

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

_EXAMPLE_DIR = Path(__file__).parent
_REPO_ROOT = _EXAMPLE_DIR.parents[2]
_TIMEOUT_MS = 15_000


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
        "CHIRP_SECRET_KEY": "browser-smoke-not-for-production",
        "PYTHONPATH": str(_REPO_ROOT / "src"),
    }
    proc = subprocess.Popen(  # noqa: S603
        ["uv", "run", "python", "-c", runner],  # noqa: S607
        cwd=str(_EXAMPLE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited early code={proc.returncode}")
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=2) as response:  # noqa: S310
                    if response.status == 200:
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
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"Chromium not installed for Playwright: {exc}")
        try:
            yield chromium
        finally:
            chromium.close()


def test_htmx_2010_fragment_oob_boost_and_sse(base_url: str, browser) -> None:
    page = browser.new_page()
    errors: list[str] = []
    requests: list[str] = []
    responses: dict[str, int] = {}
    page.on("pageerror", lambda error: errors.append(str(error)))

    def record_console(message) -> None:
        if message.type != "error":
            return
        # A finite EventSource reports its normal server-side close as an Event.
        if message.text.strip() in {"Event", "[object Event]"}:
            return
        errors.append(message.text)

    page.on("console", record_console)
    page.on("request", lambda request: requests.append(request.url))
    page.on("response", lambda response: responses.__setitem__(response.url, response.status))
    try:
        response = page.goto(f"{base_url}/baseline", wait_until="load", timeout=_TIMEOUT_MS)
        assert response is not None
        assert response.status == 200
        page.wait_for_function("() => !!window.htmx", timeout=_TIMEOUT_MS)
        assert page.evaluate("() => window.htmx.version") == "2.0.10"
        page.wait_for_timeout(2_000)
        assert any(url.endswith("/baseline/events") for url in requests), requests
        sse_script = "https://unpkg.com/htmx-ext-sse@2.2.2/sse.js"
        assert responses.get(sse_script) == 200

        page.locator("#increment").click()
        page.wait_for_function(
            "() => document.querySelector('#counter .count')?.textContent.trim() === '1'"
        )
        assert page.locator("#status").inner_text() == "count 1"

        page.locator("#boost").click()
        page.wait_for_function(
            "() => document.querySelector('#panel')?.textContent.trim() === 'boosted'"
        )
        assert page.url.endswith("/baseline/boosted")
        assert not errors, f"browser errors: {errors}"
    finally:
        page.close()
