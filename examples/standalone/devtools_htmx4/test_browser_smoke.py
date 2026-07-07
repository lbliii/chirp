"""Real-browser DevTools proof across htmx 2, htmx 4, and compatibility mode."""

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

pytestmark = pytest.mark.issue(542)

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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
    runner = (
        "import sys; sys.argv = ['app.py']; import app as _a; "
        f"_a.app.run(host='127.0.0.1', port={port})"
    )
    env = {
        **os.environ,
        "CHIRP_ENV": "production",
        "CHIRP_SECRET_KEY": "devtools-browser-proof-not-for-production",
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
                output = proc.stdout.read().decode() if proc.stdout else ""
                raise RuntimeError(f"server exited early code={proc.returncode}\n{output}")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                    if response.status == 200:
                        break
            except (
                urllib.error.URLError,
                ConnectionError,
                OSError,
            ):
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


def _exercise(page: Page, url: str) -> None:
    page.goto(url, wait_until="load", timeout=_TIMEOUT_MS)
    page.wait_for_function(
        """() => !!window.htmx && !!window.ChirpHtmxDebug &&
          window.__islandCounts?.mount === 1 &&
          document.querySelector('#safe-target-probe')?.getAttribute('hx-target') === 'this'""",
        timeout=_TIMEOUT_MS,
    )
    config_key = "transitions" if "/v4" in url else "globalViewTransitions"
    assert page.evaluate("key => window.htmx.config[key]", config_key) is True

    page.locator("#swap-button").click()
    try:
        page.wait_for_function(
            """() => {
              const state = window.ChirpHtmxDebug.getState();
              return document.querySelector('#result')?.textContent === 'Swapped' &&
                document.querySelector('#counter')?.textContent.includes('1') &&
                window.__islandCounts?.mount === 2 && window.__islandCounts?.unmount === 1 &&
                state.records.some(record => record.path.includes('/swap') && record.status === 200);
            }""",
            timeout=_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError as exc:
        state = page.evaluate(
            """() => ({
              result: document.querySelector('#result')?.outerHTML,
              counter: document.querySelector('#counter')?.outerHTML,
              state: window.ChirpHtmxDebug.getState(),
            })"""
        )
        raise AssertionError(f"success path did not settle: {state}") from exc

    success = page.evaluate(
        """() => {
          const state = window.ChirpHtmxDebug.getState();
          return {
            records: state.records.filter(record => record.path.includes('/swap')),
            oob: state.oobRecords.slice(),
            history: state.historyEvents.slice(),
          };
        }"""
    )
    assert len(success["records"]) == 1, success
    assert page.evaluate("() => window.__islandCounts") == {"mount": 2, "unmount": 1}
    record = success["records"][0]
    assert record["source"] == "<button>#swap-button"
    assert record["target"] == "#result"
    assert record["method"] == "POST"
    assert record["status"] == 200
    assert record["renderIntent"] == "fragment"
    assert record["swap"] == "outerHTML"
    assert any(name.lower().startswith("hx-") for name in record["requestHeaders"])
    assert record["timing"]["config"] <= record["timing"]["response"]
    assert record["timing"]["config"] <= record["timing"]["afterSwap"]
    assert len(success["oob"]) == 1, success
    assert success["oob"][0]["target"] == "#counter"
    page.wait_for_function(
        "() => window.ChirpHtmxDebug.getState().historyEvents.some(event => event.kind === 'push')",
        timeout=_TIMEOUT_MS,
    )
    history = page.evaluate("() => window.ChirpHtmxDebug.getState().historyEvents.slice()")
    assert len([event for event in history if event["kind"] == "push"]) == 1

    page.locator("#failure-button").click()
    page.wait_for_function(
        """() => window.ChirpHtmxDebug.getState().records.some(
          record => record.path.includes('/failure') && record.status === 503
        )""",
        timeout=_TIMEOUT_MS,
    )
    failure = page.evaluate(
        """() => {
          const state = window.ChirpHtmxDebug.getState();
          return {
            records: state.records.filter(record => record.path.includes('/failure')),
            errors: state.errors.slice(),
          };
        }"""
    )
    assert len(failure["records"]) == 1, failure
    assert failure["records"][0]["failed"] is True
    assert [error["title"] for error in failure["errors"]].count("Response Error") == 1

    page.evaluate(
        """() => {
          for (const message of [
            'Network connection failed',
            'Request timeout exceeded',
            'Target selector was not found',
            'DOM swap failed',
          ]) {
            document.dispatchEvent(new CustomEvent('htmx:error', {
              detail: {ctx: {request: {action: '/synthetic-error'}}, error: new Error(message)},
            }));
          }
        }"""
    )
    synthetic_titles = page.evaluate(
        """() => window.ChirpHtmxDebug.getState().errors
          .filter(error => error.body.includes('/synthetic-error'))
          .map(error => error.title)"""
    )
    assert sorted(synthetic_titles) == [
        "Network Error",
        "Swap Error",
        "Target Not Found",
        "Timeout",
    ]


@pytest.mark.parametrize("path", ["/", "/v4", "/v4-compat"])
def test_devtools_records_one_success_and_failure_per_action(
    base_url: str, browser, path: str
) -> None:
    page = browser.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        _exercise(page, base_url + path)
        assert not page_errors, page_errors
    finally:
        page.close()
