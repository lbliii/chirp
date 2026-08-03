"""Opt-in browser proof for the QUERY enhancement and no-JS GET floor."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = sync_api.Error
sync_playwright = sync_api.sync_playwright
pytestmark = pytest.mark.issue(534)

_EXAMPLE_DIR = Path(__file__).parent
_REPO_ROOT = _EXAMPLE_DIR.parents[2]
_TIMEOUT_MS = 20_000


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    runner = f"import sys; sys.argv = ['app.py']; from app import app; app.run(host='127.0.0.1', port={port})"
    env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
    server_python = os.environ.get("CHIRP_BROWSER_SERVER_PYTHON", sys.executable)
    proc = subprocess.Popen(  # noqa: S603
        [server_python, "-c", runner],
        cwd=str(_EXAMPLE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                raise RuntimeError(f"query_search exited early: {output}")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310, RUF100 -- fixed loopback URL
                    if response.status == 200:
                        break
            except urllib.error.URLError, ConnectionError, OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("query_search did not start")
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


def test_javascript_disabled_submits_the_bookmarkable_get_subset(base_url: str, browser) -> None:
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.set_default_timeout(_TIMEOUT_MS)
    try:
        page.goto(base_url, wait_until="load")
        page.locator('input[name="q"]').fill("python")
        page.locator('select[name="topic"]').select_option("data")
        page.locator("#year-from").fill("2026")
        page.locator("#search-submit").click()
        page.wait_for_load_state("load")

        assert "q=python" in page.url
        assert "topic=data" in page.url
        assert "year_from" not in page.url
        assert page.locator('#results[data-method="GET"]').count() == 1
        assert "Free-Threaded Query Engines" in page.locator("#results").inner_text()
    finally:
        context.close()


def test_htmx_enhancement_sends_query_and_swaps_results(base_url: str, browser) -> None:
    page = browser.new_page()
    query_requests = []
    page.on(
        "request",
        lambda request: query_requests.append(request) if request.method == "QUERY" else None,
    )
    try:
        page.goto(base_url, wait_until="load", timeout=_TIMEOUT_MS)
        page.wait_for_function("() => !!window.htmx", timeout=_TIMEOUT_MS)
        page.locator('select[name="topic"]').select_option("security")
        page.locator('[data-query-topic][value="web"]').check()
        page.locator("#year-from").fill("2025")
        page.locator("#open-access").check()
        page.locator("#search-submit").click()
        page.wait_for_function(
            "() => document.querySelector('#results')?.dataset.method === 'QUERY'",
            timeout=_TIMEOUT_MS,
        )

        assert len(query_requests) == 1
        assert "topics=web" in (query_requests[0].post_data or "")
        assert page.url.rstrip("/") == base_url
        assert "Nonce-Safe Conditional HTML" in page.locator("#results").inner_text()
    finally:
        page.close()
