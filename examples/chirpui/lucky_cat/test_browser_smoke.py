"""Opt-in browser smoke for the Lucky Cat shell (TASK 3b).

This is the real-browser counterpart to the deterministic ``test_links.py``
crawl: it boots the example on a free port and drives Chromium through
Playwright to assert the things only a browser can see —

  * ``/``, ``/portfolio``, ``/trade`` load with ZERO console errors AND zero
    page errors (the CSP regression that silently killed Alpine — every shell
    interaction dead, ``window.Alpine`` undefined — showed up *only* as console
    errors, never in the server response, so a TestClient crawl cannot catch
    it);
  * clicking an inner-rail sub-nav link actually navigates (the URL changes and
    the body is not a 404 page) — proving the seven sub-pages work through the
    boosted shell outlet, not just under a direct GET;
  * the VISIBLE collapse toggle hides the inner rail (computed
    ``display: none`` / width 0) and expands it back — the discoverability fix
    for the previously undiscoverable double-click-the-handle gesture.

It is OPT-IN: ``pytest.importorskip("playwright")`` skips the whole module when
Playwright is not installed, and a missing Chromium binary skips (not fails) at
launch. So a default ``pytest`` run of the example simply reports these as
skipped; you opt in with::

    uv run --with playwright python -m playwright install chromium
    uv run --with playwright pytest examples/chirpui/lucky_cat/test_browser_smoke.py -q

Or point it at an already-running server::

    LUCKY_CAT_BASE_URL=http://127.0.0.1:8000 \
        uv run --with playwright pytest .../test_browser_smoke.py -q

The server (when this test starts it) runs via ``uv run`` in a subprocess with
``CHIRP_SECRET_KEY`` set, on a free port, in production (non-debug) mode so the
reloader does not fork extra processes. Every browser action is bounded by an
explicit timeout, and page loads use ``wait_until="load"`` — NOT
``"networkidle"``: the shell opens long-lived SSE streams (the ticker strip,
``/ft/stream``) that never go idle, so ``networkidle`` would hang until timeout.
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

# Opt-in gate: no Playwright installed → skip the entire module cleanly.
pytest.importorskip("playwright")

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

_EXAMPLE_DIR = Path(__file__).parent
_REPO_ROOT = _EXAMPLE_DIR.parents[2]  # examples/chirpui/lucky_cat -> repo root
_ACTION_TIMEOUT_MS = 8_000
_SERVER_BOOT_TIMEOUT_S = 40.0
_ENV_BASE_URL = "LUCKY_CAT_BASE_URL"


def _free_port() -> int:
    """Grab an ephemeral port the OS just confirmed is free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_serving(base_url: str, *, proc: subprocess.Popen | None) -> None:
    """Poll the health endpoint until the server answers (or time out / die)."""
    deadline = time.monotonic() + _SERVER_BOOT_TIMEOUT_S
    health = f"{base_url}/health"
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(
                f"server process exited early with code {proc.returncode} before serving"
            )
        try:
            with urllib.request.urlopen(health, timeout=2) as resp:  # noqa: S310 (localhost)
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_err = exc
            time.sleep(0.25)
    raise RuntimeError(
        f"server did not come up at {base_url} within "
        f"{_SERVER_BOOT_TIMEOUT_S}s (last error: {last_err!r})"
    )


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """A live Lucky Cat server URL.

    If ``LUCKY_CAT_BASE_URL`` is set, point at that running server (no
    subprocess). Otherwise boot the example via ``uv run`` on a free port in a
    subprocess, with ``CHIRP_SECRET_KEY`` set and debug OFF (no reloader fork).
    """
    external = os.environ.get(_ENV_BASE_URL)
    if external:
        _wait_until_serving(external.rstrip("/"), proc=None)
        yield external.rstrip("/")
        return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "CHIRP_SECRET_KEY": os.environ.get("CHIRP_SECRET_KEY", "browser-smoke-not-for-production"),
        # Production mode: no debug reloader (which would fork a child the
        # health-poll could race) and no dev-only hot reload.
        "CHIRP_ENV": "production",
        "PYTHONPATH": str(_REPO_ROOT / "src"),
    }
    # `uv run` (never bare PYTHONPATH=src python — stale kida) launches the app
    # with --host/--port via the app's __main__ -> app.run(). We pass them as a
    # tiny inline runner so we control host/port without editing app.py.
    runner = (
        "import sys; "
        "sys.argv = ['app.py']; "
        "import app as _a; "
        f"_a.app.run(host='127.0.0.1', port={port})"
    )
    cmd = ["uv", "run", "python", "-c", runner]
    # S603: fixed argv (the runner is a constant; port is an OS-assigned int) and
    # `uv` is the mandated launcher (bare PYTHONPATH=src python ships stale kida).
    proc = subprocess.Popen(  # noqa: S603
        cmd,
        cwd=str(_EXAMPLE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_until_serving(url, proc=proc)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    """A headless Chromium. Missing browser binary → skip (not fail)."""
    with sync_playwright() as pw:
        try:
            chromium = pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"Chromium not installed for Playwright: {exc}")
        try:
            yield chromium
        finally:
            chromium.close()


def _new_page_with_console_capture(browser, base_url: str):
    """Open a page and attach console-error / page-error collectors."""
    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    page.set_default_timeout(_ACTION_TIMEOUT_MS)
    errors: list[str] = []
    page.on(
        "console",
        lambda msg: (
            errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None
        ),
    )
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    return context, page, errors


@pytest.mark.parametrize("path", ["/", "/portfolio", "/trade"])
def test_pages_load_with_zero_console_errors(browser, base_url: str, path: str) -> None:
    """Each shell page paints with no console errors and no page errors.

    This is the CSP/Alpine regression guard: a broken CSP (or a bare-package
    CDN URL) kills the entire interactive shell but returns a clean 200 — only
    the browser console reveals it."""
    context, page, errors = _new_page_with_console_capture(browser, base_url)
    try:
        # wait_until="load" — NOT "networkidle": the SSE ticker/ft streams never
        # idle, so networkidle would hang until the timeout.
        page.goto(path, wait_until="load")
        # Give Alpine a beat to initialize and surface any boot-time errors.
        page.wait_for_selector(".chirpui-app-shell", timeout=_ACTION_TIMEOUT_MS)
        assert not errors, f"{path} produced browser errors: {errors}"
        # The shell actually mounted Alpine (the CSP-kill symptom is undefined).
        assert page.evaluate("() => typeof window.Alpine !== 'undefined'"), (
            f"{path}: window.Alpine is undefined — the shell did not initialize"
        )
    finally:
        context.close()


def test_inner_rail_subnav_navigates(browser, base_url: str) -> None:
    """Clicking a previously-dead inner-rail sub-link navigates (URL changes, no
    404 body) — proving the sub-pages resolve through the boosted shell outlet."""
    context, page, errors = _new_page_with_console_capture(browser, base_url)
    try:
        page.goto("/portfolio", wait_until="load")
        page.wait_for_selector(".chirpui-app-shell", timeout=_ACTION_TIMEOUT_MS)
        # The Portfolio room's inner rail links to /portfolio/orders.
        link = page.locator('a[href="/portfolio/orders"]').first
        link.wait_for(state="visible", timeout=_ACTION_TIMEOUT_MS)
        link.click()
        # Boosted nav swaps #main and pushes the URL; wait for the URL to change.
        page.wait_for_url("**/portfolio/orders", timeout=_ACTION_TIMEOUT_MS)
        assert page.url.endswith("/portfolio/orders"), page.url
        # The sub-page rendered its real heading (not a 404 / error body).
        body = page.locator("body").inner_text(timeout=_ACTION_TIMEOUT_MS)
        assert "Open orders" in body, body[:300]
        assert "404" not in body, body[:300]
        assert "Not Found" not in body, body[:300]
        assert not errors, f"sub-nav produced browser errors: {errors}"
    finally:
        context.close()


def test_collapse_toggle_hides_and_restores_inner_rail(browser, base_url: str) -> None:
    """The visible collapse toggle hides the inner rail (computed display:none /
    width 0) and expands it back — the discoverability fix."""
    context, page, errors = _new_page_with_console_capture(browser, base_url)
    try:
        page.goto("/", wait_until="load")
        page.wait_for_selector(".chirpui-app-shell", timeout=_ACTION_TIMEOUT_MS)

        inner_rail = page.locator(".luckycat-inner-rail").first
        inner_rail.wait_for(state="visible", timeout=_ACTION_TIMEOUT_MS)

        def inner_metrics() -> tuple[str, float]:
            return tuple(  # type: ignore[return-value]
                page.evaluate(
                    """() => {
                        const el = document.querySelector('.luckycat-inner-rail');
                        if (!el) return ['missing', 0];
                        const cs = getComputedStyle(el);
                        return [cs.display, el.getBoundingClientRect().width];
                    }"""
                )
            )

        # Baseline: expanded — visible with a non-zero width.
        display0, width0 = inner_metrics()
        assert display0 != "none", (display0, width0)
        assert width0 > 0, (display0, width0)

        # Click the visible toggle (the inner-rail copy is on screen while expanded).
        toggle = page.locator("[data-luckycat-rail-toggle]").first
        toggle.wait_for(state="visible", timeout=_ACTION_TIMEOUT_MS)
        toggle.click()
        # The collapsed class lands on the shell and the inner rail is removed
        # from layout (display:none in lucky-cat.css → width 0).
        page.wait_for_function(
            """() => {
                const el = document.querySelector('.luckycat-inner-rail');
                if (!el) return false;
                const cs = getComputedStyle(el);
                return cs.display === 'none' || el.getBoundingClientRect().width === 0;
            }""",
            timeout=_ACTION_TIMEOUT_MS,
        )
        display1, width1 = inner_metrics()
        assert display1 == "none" or width1 == 0, (display1, width1)

        # Expand again via the always-reachable icon-rail copy of the toggle.
        page.locator("[data-luckycat-rail-toggle]").first.click()
        page.wait_for_function(
            """() => {
                const el = document.querySelector('.luckycat-inner-rail');
                if (!el) return false;
                const cs = getComputedStyle(el);
                return cs.display !== 'none' && el.getBoundingClientRect().width > 0;
            }""",
            timeout=_ACTION_TIMEOUT_MS,
        )
        display2, width2 = inner_metrics()
        assert display2 != "none", (display2, width2)
        assert width2 > 0, (display2, width2)

        assert not errors, f"collapse toggle produced browser errors: {errors}"
    finally:
        context.close()
