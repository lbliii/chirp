"""Real-browser DevTools proof for HTTP QUERY fragment and stream records (#529)."""

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
pytestmark = pytest.mark.issue(529)

_REPO_ROOT = Path(__file__).parents[2]
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
        "import sys; "
        "from tests.contracts.query_devtools_app import app; "
        f"sys.argv = ['query_devtools_app.py']; app.run(host='127.0.0.1', port={port})"
    )
    env = {
        **os.environ,
        "CHIRP_ENV": "development",
        "PYTHONPATH": str(_REPO_ROOT / "src"),
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", runner],
        cwd=str(_REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                raise RuntimeError(f"server exited early code={proc.returncode}: {output}")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
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


def _query(page, path: str) -> None:
    page.evaluate(
        """path => window.htmx.ajax("QUERY", path, {
          source: document.querySelector("#query-source"),
          target: "#query-target",
          swap: "innerHTML",
          headers: {"Content-Type": "application/x-www-form-urlencoded"},
          values: {term: "chirp"}
        })""",
        path,
    )
    page.wait_for_function(
        "path => window.ChirpHtmxDebug.getState().records.some(r => r.path === path && r.timing.response)",
        arg=path,
        timeout=_TIMEOUT_MS,
    )


def test_query_devtools_records_fragment_stream_timing_and_error(base_url: str, browser) -> None:
    page = browser.new_page()
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    try:
        response = page.goto(base_url, wait_until="load", timeout=_TIMEOUT_MS)
        assert response is not None
        assert response.status == 200
        page.wait_for_function(
            "() => !!window.htmx && !!window.ChirpHtmxDebug", timeout=_TIMEOUT_MS
        )

        _query(page, "/query/page")
        fragment = page.evaluate(
            "() => window.ChirpHtmxDebug.getState().records.find(r => r.path === '/query/page')"
        )
        assert fragment["method"] == "QUERY"
        assert fragment["methodSemantics"] == "safe"
        assert fragment["status"] == 200
        assert fragment["target"] == "#query-target"
        assert fragment["renderIntent"] == "fragment"
        assert fragment["contentType"].startswith("text/html")
        assert fragment["timing"]["response"] >= fragment["timing"]["sent"]
        assert fragment["returnTrace"]["method"] == "QUERY"
        assert fragment["returnTrace"]["request_content_type"].startswith(
            "application/x-www-form-urlencoded"
        )
        assert fragment["returnTrace"]["block"] == "content"

        _query(page, "/query/stream")
        stream = page.evaluate(
            "() => window.ChirpHtmxDebug.getState().records.find(r => r.path === '/query/stream')"
        )
        assert stream["method"] == "QUERY"
        assert stream["methodSemantics"] == "safe"
        assert stream["status"] == 200
        assert stream["returnTrace"]["return_type"] == "Stream"
        assert stream["returnTrace"]["streaming"] is True
        assert "query-browser-stream" in stream["bodyPreview"]

        _query(page, "/query/invalid")
        invalid = page.evaluate(
            "() => window.ChirpHtmxDebug.getState().records.find(r => r.path === '/query/invalid')"
        )
        assert invalid["method"] == "QUERY"
        assert invalid["methodSemantics"] == "safe"
        assert invalid["status"] == 422
        assert invalid["failed"] is True
        assert invalid["returnTrace"]["return_type"] == "ValidationError"
        assert "query-browser-invalid" in invalid["bodyPreview"]
        assert not page_errors, page_errors
        assert console_errors
        assert all("422" in error for error in console_errors), console_errors
    finally:
        page.close()
