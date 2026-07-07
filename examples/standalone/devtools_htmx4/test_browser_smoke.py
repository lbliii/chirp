"""Real-browser DevTools proof across htmx 2, htmx 4, and compatibility mode."""

from __future__ import annotations

import contextlib
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


@contextlib.contextmanager
def _serve_app(app_name: str) -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    runner = (
        "import sys; sys.argv = ['app.py']; import app as _a; "
        f"_a.{app_name}.run(host='127.0.0.1', port={port})"
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited early code={proc.returncode}")
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
def base_url() -> Iterator[str]:
    with _serve_app("app") as url:
        yield url


@pytest.fixture(scope="module")
def preview_base_url() -> Iterator[str]:
    with _serve_app("preview_app") as url:
        yield url


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

    page.locator("#inspect-button").click()
    page.wait_for_function(
        """() => {
          const metadata = document.querySelector('#metadata');
          const records = window.ChirpHtmxDebug.getState().records;
          return metadata?.dataset.targetId === 'metadata' &&
            metadata?.dataset.trigger === 'inspect-button' &&
            records.some(record => record.path.includes('/inspect') && record.status === 200);
        }""",
        timeout=_TIMEOUT_MS,
    )
    metadata = page.locator("#metadata")
    inspect_records = page.evaluate(
        """() => window.ChirpHtmxDebug.getState().records
          .filter(record => record.path.includes('/inspect'))"""
    )
    assert len(inspect_records) == 1, inspect_records
    headers = {name.lower(): value for name, value in inspect_records[0]["requestHeaders"].items()}
    assert metadata.get_attribute("data-target-id") == "metadata"
    assert metadata.get_attribute("data-trigger") == "inspect-button"
    if "/v4" in url:
        assert metadata.get_attribute("data-target-raw") == "div#metadata"
        assert metadata.get_attribute("data-source-raw") == "button#inspect-button"
        assert metadata.get_attribute("data-source-id") == "inspect-button"
        assert metadata.get_attribute("data-source-tag") == "button"
        assert metadata.get_attribute("data-trigger-name") == ""
        assert metadata.get_attribute("data-request-type") == "partial"
        assert metadata.get_attribute("data-accept") == "text/html"
        assert headers["hx-target"] == "div#metadata"
        assert headers["hx-source"] == "button#inspect-button"
        assert headers["hx-request-type"] == "partial"
        assert headers["accept"] == "text/html"
    else:
        assert metadata.get_attribute("data-target-raw") == "metadata"
        assert metadata.get_attribute("data-source-raw") == ""
        assert metadata.get_attribute("data-source-id") == ""
        assert metadata.get_attribute("data-trigger-name") == "inspect-action"
        assert metadata.get_attribute("data-request-type") == ""
        assert headers["hx-target"] == "metadata"
        assert headers["hx-trigger"] == "inspect-button"

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


@pytest.mark.issue(545)
def test_managed_preview_bundle_csp_sse_and_devtools(
    preview_base_url: str,
    browser,
) -> None:
    page = browser.new_page()
    page.set_default_timeout(5_000)
    errors: list[str] = []
    requests: list[str] = []
    swap_headers: dict[str, str] = {}
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )

    def record_request(request) -> None:
        requests.append(request.url)
        if request.url.endswith("/swap"):
            swap_headers.update(request.headers)

    page.on("request", record_request)
    page.add_init_script(
        """window.__previewEvents = {legacy: 0, native: 0};
        function recordsResult(event) {
          const detail = event.detail || {};
          const target = detail.target || (detail.ctx && detail.ctx.target);
          return target && target.id === "result";
        }
        document.addEventListener("htmx:afterSwap", (event) => {
          if (recordsResult(event)) window.__previewEvents.legacy++;
        });
        document.addEventListener("htmx:after:swap", (event) => {
          if (recordsResult(event)) window.__previewEvents.native++;
        });"""
    )
    try:
        response = page.goto(preview_base_url, wait_until="load", timeout=_TIMEOUT_MS)
        assert response is not None
        assert response.status == 200
        page.wait_for_function(
            "() => !!window.htmx && !!window.ChirpHtmxDebug",
            timeout=_TIMEOUT_MS,
        )

        compatibility = page.evaluate("() => window.ChirpHtmxDebug.getHtmxCompatibility()")
        scripts = page.locator("script").evaluate_all(
            "items => items.map(item => ({src: item.src, chirp: item.dataset.chirp, "
            "tier: item.dataset.chirpHtmxTier, version: item.dataset.chirpHtmxVersion}))"
        )
        assert compatibility["configuredTier"] == "4-preview", {
            "compatibility": compatibility,
            "scripts": scripts,
        }
        assert compatibility["configuredVersion"] == "4.0.0-beta5"
        assert compatibility["liveVersion"] == "4.0.0-beta5"
        assert compatibility["extensionRoles"] == ["compat", "sse"]
        assert compatibility["duplicates"] == []
        assert compatibility["compatibilityState"] == "matched"
        assert [asset["role"] for asset in compatibility["sources"]] == [
            "core",
            "compat",
            "sse",
        ]

        csp = response.headers.get("content-security-policy", "")
        nonce = csp.split("'nonce-", 1)[1].split("'", 1)[0]
        script_nonces = page.locator('script[data-chirp-htmx-tier="4-preview"]').evaluate_all(
            "scripts => scripts.map(script => script.nonce)"
        )
        assert script_nonces == [nonce, nonce, nonce]

        page.locator("#preview-swap").click()
        page.wait_for_function(
            "() => document.querySelector('#result')?.textContent === 'Swapped'",
            timeout=_TIMEOUT_MS,
        )
        assert "text/event-stream" in swap_headers.get("accept", "")
        events = page.evaluate("() => window.__previewEvents")
        assert events["legacy"] == 1
        assert events["native"] == 1

        assert len([url for url in requests if "htmx.org@4.0.0-beta5" in url]) == 3

        page.evaluate(
            """() => document.querySelector('[data-chirp="htmx"]')
              .setAttribute('data-chirp-htmx-version', '4.0.0-beta6')"""
        )
        mismatch = page.evaluate("() => window.ChirpHtmxDebug.getHtmxCompatibility()")
        assert mismatch["compatibilityState"] == "mismatch"
        assert not errors, errors
    finally:
        page.close()


@pytest.mark.issue(548)
def test_managed_preview_default_contracts(
    preview_base_url: str,
    browser,
) -> None:
    page = browser.new_page()
    page.set_default_timeout(_TIMEOUT_MS)
    queue_order: list[str] = []
    delete_payloads: list[str | None] = []

    def record_request(request) -> None:
        if request.url.endswith("/queue"):
            queue_order.append("request")
        if "/delete" in request.url:
            delete_payloads.append(request.post_data)

    def record_response(response) -> None:
        if response.url.endswith("/queue"):
            queue_order.append("response")

    page.on("request", record_request)
    page.on("response", record_response)
    try:
        page.goto(preview_base_url, wait_until="load")
        page.wait_for_function("() => !!window.htmx")

        policy = page.evaluate(
            """() => ({
              noSwap: window.htmx.config.noSwap,
              timeout: window.htmx.config.defaultTimeout,
              inheritance: window.htmx.config.implicitInheritance,
            })"""
        )
        assert policy == {
            "noSwap": [204, 304, "5xx"],
            "timeout": 60_000,
            "inheritance": True,
        }
        compatibility = page.evaluate("() => window.ChirpHtmxDebug.getHtmxCompatibility()")
        assert compatibility["clientPolicy"]["declared"] == {
            "noSwap": [204, 304, "5xx"],
            "defaultTimeout": 60_000,
            "compat": {"swapErrorResponseCodes": True},
        }
        assert compatibility["clientPolicy"]["live"]["queue"] == "hx-sync"

        page.locator("#inherit-load").click()
        page.wait_for_function(
            "() => document.querySelector('#inherited')?.textContent.includes('Inherited')"
        )

        page.locator("#validation-load").click()
        page.wait_for_function(
            "() => document.querySelector('#validation')?.textContent === 'Validation failed'"
        )

        page.locator("#failure-load").click()
        page.wait_for_timeout(100)
        assert page.locator("#shell").count() == 1
        assert page.locator("#shell").inner_text().startswith("Managed htmx 4 preview")

        page.locator("#oob-load").click()
        page.wait_for_function(
            """() => document.querySelector('#main-result')?.textContent.includes('Main updated') &&
              document.querySelector('#oob-result')?.textContent.includes('OOB updated')"""
        )
        assert page.evaluate("() => window.__swapOrder.slice(0, 2)") == ["main", "oob"]

        page.locator("#delete-no-fields").click()
        page.wait_for_function(
            "() => document.querySelector('#delete-result')?.textContent.includes('missing')"
        )
        page.reload(wait_until="load")
        page.wait_for_function("() => !!window.htmx")
        page.locator("#delete-with-fields").click()
        page.wait_for_timeout(250)
        assert page.locator("#delete-result").inner_text().strip() == "42", delete_payloads

        page.locator("#slow-load").click()
        page.wait_for_timeout(300)
        assert page.locator("#slow-result").inner_text() == "Ready"
        timeout_errors = page.evaluate("() => window.ChirpHtmxDebug.getState().errors.slice()")
        assert "Timeout" in [error["title"] for error in timeout_errors], timeout_errors

        page.evaluate(
            """() => {
              document.querySelector('#queue-load').click();
              document.querySelector('#queue-load').click();
            }"""
        )
        page.wait_for_function(
            "() => document.querySelector('#queue-result')?.textContent.includes('Queued')"
        )
        page.wait_for_timeout(250)
        assert queue_order == ["request", "response", "request", "response"]
        queue_records = page.evaluate(
            """() => window.ChirpHtmxDebug.getState().records
              .filter(record => record.path.includes('/queue'))"""
        )
        assert len(queue_records) == 2
        assert all(
            record["synchronization"] == {"owner": "this", "strategy": "queue all"}
            for record in queue_records
        )

        page.locator("#history-next").click()
        page.wait_for_function("() => window.location.pathname === '/history/next'")
        page.go_back(wait_until="load")
        assert page.url.rstrip("/") == preview_base_url.rstrip("/")
        assert page.locator("#shell").count() == 1
        history_kinds = page.evaluate(
            "() => window.ChirpHtmxDebug.getState().historyEvents.map(event => event.kind)"
        )
        assert "push" in history_kinds
        assert "restore" in history_kinds
    finally:
        page.close()


@pytest.mark.issue(549)
def test_preview_timing_migration_uses_rendered_data_and_target_lifecycle(
    preview_base_url: str,
    browser,
) -> None:
    page = browser.new_page()
    try:
        page.goto(preview_base_url, wait_until="load", timeout=_TIMEOUT_MS)
        page.wait_for_function("() => !!window.htmx && Array.isArray(window.__timingEvents)")
        page.locator("#timing-load").click()
        page.wait_for_function("() => window.__timingEvents.length === 2")
        assert page.evaluate("() => window.__timingEvents") == [
            {
                "phase": "before-settle",
                "event": "dom-updated",
                "target": "timing-result",
            },
            {
                "phase": "after-settle",
                "event": "ui-settled",
                "target": "timing-result",
            },
        ]
    finally:
        page.close()
