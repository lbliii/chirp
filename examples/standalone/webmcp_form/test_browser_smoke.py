"""Chrome 149 progressive-enhancement proof for experimental WebMCP (#576)."""

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

pytest.importorskip("playwright")
pytestmark = pytest.mark.issue(576)

from playwright.sync_api import Browser, Error, Route, sync_playwright

_CHROME_FOR_TESTING = "149.0.7827.55"
_EXAMPLE_DIR = Path(__file__).parent
_REPO_ROOT = _EXAMPLE_DIR.parents[2]
_TIMEOUT_MS = 15_000


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
        "CHIRP_SECRET_KEY": "browser-smoke-not-for-production",
        "PYTHONPATH": str(_REPO_ROOT / "src"),
    }
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", runner],
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
            proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Chrome for Testing is not installed: {exc}")
        assert chromium.version == _CHROME_FOR_TESTING
        try:
            yield chromium
        finally:
            chromium.close()


def _submit_native_form(browser: Browser, base_url: str, *, disable_tools: bool) -> None:
    context = browser.new_context(java_script_enabled=False)
    if disable_tools:

        def deny_tools(route: Route) -> None:
            response = route.fetch()
            route.fulfill(
                response=response,
                headers={**response.headers, "permissions-policy": "tools=()"},
            )

        context.route(f"{base_url}/", deny_tools)
    page = context.new_page()
    page.set_default_timeout(_TIMEOUT_MS)
    try:
        response = page.goto(base_url, wait_until="load")
        assert response is not None
        assert response.status == 200
        if disable_tools:
            assert response.header_value("permissions-policy") == "tools=()"
        form = page.locator("#task-form")
        assert form.get_attribute("toolname") == "tasks.create"
        assert form.get_attribute("tooldescription") == "Create a task"
        assert form.get_attribute("toolautosubmit") is None
        page.locator('input[name="title"]').fill("Native fallback")
        page.locator('input[name="priority"]').fill("2")
        button = page.locator('button[type="submit"]')
        box = button.bounding_box()
        assert box is not None
        session = context.new_cdp_session(page)
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        with page.expect_response(lambda item: item.url.endswith("/tasks")) as captured:
            session.send(
                "Input.dispatchMouseEvent",
                {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                },
            )
            session.send(
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                },
            )
        assert captured.value.status == 303
        page.wait_for_load_state("load")
        assert page.url == f"{base_url}/"
        assert page.locator("h1").inner_text() == "Create a task"
    finally:
        context.close()


def test_chrome_149_without_webmcp_keeps_complete_native_form(
    browser: Browser,
    base_url: str,
) -> None:
    _submit_native_form(browser, base_url, disable_tools=False)


def test_permissions_policy_denial_does_not_disable_human_fallback(
    browser: Browser,
    base_url: str,
) -> None:
    _submit_native_form(browser, base_url, disable_tools=True)


def test_chrome_149_htmx_submission_uses_same_handler(
    browser: Browser,
    base_url: str,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(_TIMEOUT_MS)
    try:
        page.goto(base_url, wait_until="load")
        page.wait_for_function("() => !!window.htmx")
        page.locator('input[name="title"]').fill("Htmx path")
        page.locator('input[name="priority"]').fill("3")
        with page.expect_response(lambda response: response.url.endswith("/tasks")) as captured:
            page.locator('button[type="submit"]').click()
        response = captured.value
        assert response.status == 200
        assert response.request.header_value("hx-request") == "true"
        page.wait_for_url(f"{base_url}/")
    finally:
        context.close()
