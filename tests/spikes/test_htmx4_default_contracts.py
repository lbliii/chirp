"""Opt-in browser proof for RFC 013 htmx 4 defaults (#548)."""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HTMX4_COMMIT = "5300af9e7af8b196f9fbf806cab79a5780b62291"
CORE_SHA256 = "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68"
COMPAT_SHA256 = "7d7fe881d6ae6d4e661b0113e8504bb15acfc1dc1970f07db109bb20c432e53d"

PAGE = b"""<!doctype html>
<html><head>
<meta name="htmx-config" content='{"noSwap":[204,304,"5xx"],"compat":{"swapErrorResponseCodes":true}}'>
<script defer src="/core.js"></script><script defer src="/compat.js"></script>
</head><body>
<div hx-target="#inherited"><button id="inherit-load" hx-get="/inherit">inherit</button></div>
<div id="inherited">before inherit</div>
<button id="validation-load" hx-get="/validation" hx-target="#validation">422</button>
<div id="validation">before validation</div>
<section id="shell">shell safe</section>
<button id="failure-load" hx-get="/failure" hx-target="#shell">500</button>
<button id="oob-load" hx-get="/oob" hx-target="#main">oob</button>
<div id="main">before main</div><div id="oob">before oob</div>
<form><input name="token" value="secret"><button id="delete-load" hx-delete="/delete" hx-target="#delete-result">delete</button></form>
<div id="delete-result">before delete</div>
<script>
window.swapOrder=[];
new MutationObserver(() => window.swapOrder.push("main")).observe(document.getElementById("main"), {childList:true});
new MutationObserver(() => window.swapOrder.push("oob")).observe(document.getElementById("oob"), {childList:true});
</script>
</body></html>"""


@dataclass(slots=True)
class State:
    core: bytes
    compat: bytes
    delete_paths: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class Server(ThreadingHTTPServer):
    state: State


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/core.js":
            self._send(200, self.server.state.core, "text/javascript")
        elif self.path == "/compat.js":
            self._send(200, self.server.state.compat, "text/javascript")
        elif self.path == "/inherit":
            self._send(200, b"<strong id=inherited-new>inherited</strong>")
        elif self.path == "/validation":
            self._send(422, b"<strong id=validation-error>invalid</strong>")
        elif self.path == "/failure":
            self._send(500, b"<strong id=shell-destroyed>failure</strong>")
        elif self.path == "/oob":
            body = b"<span id=main-new>main</span><div id=oob hx-swap-oob=innerHTML><span id=oob-new>oob</span></div>"
            self._send(200, body)
        else:
            self.send_error(404)

    def do_DELETE(self) -> None:
        with self.server.state.lock:
            self.server.state.delete_paths.append(self.path)
        self._send(200, b"<strong id=deleted>deleted</strong>")

    def _send(
        self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def serve(state: State):
    server = Server(("127.0.0.1", 0), Handler)
    server.state = state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.issue(548)
@pytest.mark.integration
def test_preview_default_contracts_in_browser() -> None:
    if os.environ.get("CHIRP_HTMX4_DEFAULTS_SPIKE") != "1":
        pytest.skip("set CHIRP_HTMX4_DEFAULTS_SPIKE=1")
    root_raw = os.environ.get("HTMX4_SOURCE_ROOT")
    if not root_raw:
        pytest.fail("HTMX4_SOURCE_ROOT must point to the pinned htmx checkout")
    root = Path(root_raw)
    core = root / "dist" / "htmx.min.js"
    compat = root / "dist" / "ext" / "htmx-2-compat.min.js"
    assert sha256(core) == CORE_SHA256
    assert sha256(compat) == COMPAT_SHA256

    from playwright.sync_api import sync_playwright

    state = State(core.read_bytes(), compat.read_bytes())
    with serve(state) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base_url)
        assert page.evaluate("htmx.config.defaultTimeout") == 60000
        assert page.evaluate("htmx.config.implicitInheritance") is True

        page.locator("#inherit-load").click()
        page.locator("#inherited-new").wait_for()
        page.locator("#validation-load").click()
        page.locator("#validation-error").wait_for()
        page.locator("#failure-load").click()
        page.wait_for_timeout(100)
        assert page.locator("#shell").inner_text() == "shell safe"
        assert page.locator("#shell-destroyed").count() == 0

        page.locator("#oob-load").click()
        page.locator("#main-new").wait_for()
        page.locator("#oob-new").wait_for()
        assert page.evaluate("window.swapOrder")[:2] == ["main", "oob"]

        page.locator("#delete-load").click()
        page.locator("#deleted").wait_for()
        browser.close()

    with state.lock:
        assert state.delete_paths == ["/delete"]
