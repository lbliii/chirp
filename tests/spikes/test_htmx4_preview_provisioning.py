"""Opt-in browser proof for RFC 012 htmx 4 preview provisioning (#545)."""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HTMX4_COMMIT = "5300af9e7af8b196f9fbf806cab79a5780b62291"
CORE_SHA256 = "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68"
COMPAT_SHA256 = "7d7fe881d6ae6d4e661b0113e8504bb15acfc1dc1970f07db109bb20c432e53d"
SSE_SHA256 = "fcc844a52779d8450c1c4796feea8d038943f908b9ee974322c276230e6c86cc"
NONCE = "CHIRP-PREVIEW-NONCE"

PAGE = f"""<!doctype html>
<html><head>
<script defer nonce="{NONCE}" src="/core.js" data-chirp="htmx" data-chirp-htmx-tier="4-preview" data-chirp-htmx-version="4.0.0-beta5"></script>
<script defer nonce="{NONCE}" src="/compat.js" data-chirp="htmx-extension" data-chirp-htmx-extension="compat" data-chirp-htmx-tier="4-preview" data-chirp-htmx-version="4.0.0-beta5"></script>
<script defer nonce="{NONCE}" src="/sse.js" data-chirp="htmx-extension" data-chirp-htmx-extension="sse" data-chirp-htmx-tier="4-preview" data-chirp-htmx-version="4.0.0-beta5"></script>
</head><body>
<button id="load" hx-get="/swap" hx-target="#output">Load</button>
<div id="output">before</div>
<button id="stream-load" hx-get="/events" hx-target="#stream">Stream</button>
<div id="stream"></div>
<script nonce="{NONCE}">
document.body.addEventListener("htmx:afterSwap", () => document.body.dataset.compat = "yes");
document.body.addEventListener("htmx:after:swap", () => document.body.dataset.native = "yes");
</script>
</body></html>""".encode()


@dataclass(slots=True)
class State:
    core: bytes
    compat: bytes
    sse: bytes
    requests: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


class Server(ThreadingHTTPServer):
    state: State


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(200)
            self.send_header(
                "Content-Security-Policy",
                f"default-src \x27self\x27; script-src \x27nonce-{NONCE}\x27; connect-src \x27self\x27",
            )
            self._finish(PAGE, "text/html; charset=utf-8")
            return
        assets = {
            "/core.js": self.server.state.core,
            "/compat.js": self.server.state.compat,
            "/sse.js": self.server.state.sse,
        }
        if self.path in assets:
            with self.server.state.lock:
                self.server.state.requests[self.path] = (
                    self.server.state.requests.get(self.path, 0) + 1
                )
            self.send_response(200)
            self._finish(assets[self.path], "text/javascript; charset=utf-8")
            return
        if self.path == "/swap":
            self.send_response(200)
            self._finish(b"<strong id=swapped>after</strong>", "text/html; charset=utf-8")
            return
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: <span id=sse-loaded>streamed</span>" + bytes((10, 10)))
            self.wfile.flush()
            time.sleep(0.05)
            self.wfile.write(b"event: done" + bytes((10,)) + b"data: close" + bytes((10, 10)))
            self.wfile.flush()
            return
        self.send_error(404)

    def _finish(self, body: bytes, content_type: str) -> None:
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


@pytest.mark.issue(545)
@pytest.mark.integration
def test_preview_bundle_loads_once_in_order_under_nonce_csp() -> None:
    if os.environ.get("CHIRP_HTMX4_PROVISIONING_SPIKE") != "1":
        pytest.skip("set CHIRP_HTMX4_PROVISIONING_SPIKE=1")
    root_raw = os.environ.get("HTMX4_SOURCE_ROOT")
    if not root_raw:
        pytest.fail("HTMX4_SOURCE_ROOT must point to the pinned htmx checkout")
    root = Path(root_raw)
    core = root / "dist" / "htmx.min.js"
    compat = root / "dist" / "ext" / "htmx-2-compat.min.js"
    sse = root / "dist" / "ext" / "hx-sse.min.js"
    assert sha256(core) == CORE_SHA256
    assert sha256(compat) == COMPAT_SHA256
    assert sha256(sse) == SSE_SHA256

    from playwright.sync_api import sync_playwright

    state = State(core.read_bytes(), compat.read_bytes(), sse.read_bytes())
    with serve(state) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.goto(base_url)
        assert page.evaluate("typeof htmx") == "object", errors
        page.locator("#stream-load").click()
        page.locator("#sse-loaded").first.wait_for(timeout=10_000)
        assert page.locator("#sse-loaded").count() == 1
        page.locator("#load").click()
        page.locator("#swapped").wait_for(timeout=10_000)
        assert page.evaluate("htmx.version") == "4.0.0-beta5"
        assert page.locator("body").get_attribute("data-compat") == "yes"
        assert page.locator("body").get_attribute("data-native") == "yes"
        assert errors == []
        browser.close()

    with state.lock:
        assert state.requests == {"/core.js": 1, "/compat.js": 1, "/sse.js": 1}
