"""Opt-in browser spike for the htmx 4 SSE migration RFC (#550).

Run with an exact upstream checkout so the normal test suite stays offline::

    git clone --depth 1 --branch v4.0.0-beta5 \
      https://github.com/bigskysoftware/htmx.git /tmp/htmx-4.0.0-beta5
    CHIRP_HTMX4_SSE_SPIKE=1 \
    HTMX4_SOURCE_ROOT=/tmp/htmx-4.0.0-beta5 \
      uv run pytest tests/spikes/test_htmx4_sse_preview.py -q
"""

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
HTMX4_SHA256 = "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68"
HX_SSE_SHA256 = "aa9aa14f10ddbf13a8fc4f8bbd6bc14e0b09b64d668d17e831e69763eac72558"

_PAGE = b"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <script src="/htmx.min.js"></script>
    <script src="/hx-sse.js"></script>
  </head>
  <body>
    <div id="stream" hx-sse:connect="/events" hx-sse:close="done">
      <span id="seed">seed</span>
    </div>
    <div id="signal-stream" hx-sse:connect="/signals" hx-sse:close="done">
      <span id="balance-a" data-chirp-signal="balance">seed a</span>
      <span id="balance-b" data-chirp-signal="balance">seed b</span>
    </div>
    <ul id="feed"></ul>
    <div id="status">status seed</div>
    <div id="count">0</div>
    <script>
      document.getElementById("stream").addEventListener("notice", (event) => {
        document.body.dataset.notice = event.detail.data;
      });
    </script>
  </body>
</html>
"""

_INITIAL_EVENTS = (
    'id: 1\ndata: <span id="main-message">main one</span>\n\n',
    'id: 2\ndata: <div id="status" hx-swap-oob="innerHTML">OOB one</div>\n\n',
    "id: 3\ndata: "
    '<hx-partial hx-target="#feed" hx-swap="beforeend">'
    '<li id="feed-one">feed one</li></hx-partial>'
    '<hx-partial hx-target="#count"><span id="count-one">1</span></hx-partial>\n\n',
    "id: 4\nevent: notice\ndata: named payload\n\n",
    'id: 5\ndata: <span id="reconnect-marker">before reconnect</span>\n\n',
    "data: \n\n",
)

_RECONNECT_EVENTS = (
    "id: 6\ndata: "
    '<hx-partial hx-target="#feed" hx-swap="beforeend">'
    '<li id="feed-two">feed two</li></hx-partial>\n\n',
    "event: done\ndata: close\n\n",
)

_SIGNAL_EVENTS = (
    "data: "
    "<hx-partial hx-target=\"[data-chirp-signal='balance']\">"
    '<strong class="balance-value">9</strong></hx-partial>\n\n',
    "event: done\ndata: close\n\n",
)


@dataclass(slots=True)
class _SpikeState:
    htmx: bytes
    hx_sse: bytes
    last_event_ids: list[str | None] = field(default_factory=list)
    signal_requests: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class _SpikeServer(ThreadingHTTPServer):
    state: _SpikeState


class _Handler(BaseHTTPRequestHandler):
    server: _SpikeServer

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        if self.path == "/":
            self._send_bytes(_PAGE, "text/html; charset=utf-8")
            return
        if self.path == "/htmx.min.js":
            self._send_bytes(self.server.state.htmx, "text/javascript; charset=utf-8")
            return
        if self.path == "/hx-sse.js":
            self._send_bytes(self.server.state.hx_sse, "text/javascript; charset=utf-8")
            return
        if self.path == "/events":
            self._send_events()
            return
        if self.path == "/signals":
            with self.server.state.lock:
                self.server.state.signal_requests += 1
            self._start_event_stream()
            self._send_event_frames(_SIGNAL_EVENTS)
            return
        self.send_error(404)

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_events(self) -> None:
        last_event_id = self.headers.get("Last-Event-ID")
        with self.server.state.lock:
            self.server.state.last_event_ids.append(last_event_id)

        self._start_event_stream()

        events = _RECONNECT_EVENTS if last_event_id == "5" else _INITIAL_EVENTS
        self._send_event_frames(events)

    def _start_event_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def _send_event_frames(self, events: tuple[str, ...]) -> None:
        try:
            for event in events:
                self.wfile.write(event.encode())
                self.wfile.flush()
                time.sleep(0.05)
        except BrokenPipeError, ConnectionResetError:
            pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def _serve(state: _SpikeState):
    server = _SpikeServer(("127.0.0.1", 0), _Handler)
    server.state = state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.issue(550)
@pytest.mark.integration
def test_htmx4_sse_preview_browser_contract() -> None:
    if os.environ.get("CHIRP_HTMX4_SSE_SPIKE") != "1":
        pytest.skip("set CHIRP_HTMX4_SSE_SPIKE=1 to run the pinned browser spike")

    source_root_raw = os.environ.get("HTMX4_SOURCE_ROOT")
    if not source_root_raw:
        pytest.fail("HTMX4_SOURCE_ROOT must point to the pinned htmx checkout")
    source_root = Path(source_root_raw)
    htmx_path = source_root / "dist" / "htmx.min.js"
    hx_sse_path = source_root / "dist" / "ext" / "hx-sse.js"
    assert _sha256(htmx_path) == HTMX4_SHA256
    assert _sha256(hx_sse_path) == HX_SSE_SHA256

    from playwright.sync_api import sync_playwright

    state = _SpikeState(htmx=htmx_path.read_bytes(), hx_sse=hx_sse_path.read_bytes())
    with _serve(state) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        browser_messages: list[str] = []
        page.on("console", lambda message: browser_messages.append(message.text))
        page.on("pageerror", lambda error: browser_messages.append(str(error)))
        page.goto(base_url)
        page.locator("#feed-two").wait_for(timeout=15_000)
        page.locator(".balance-value").first.wait_for(timeout=15_000)
        assert page.locator(".balance-value").count() == 2, "\n".join(browser_messages)

        assert page.locator("#stream").inner_text() == "before reconnect"
        assert page.locator("#status").inner_text() == "OOB one"
        assert page.locator("#feed-one").inner_text() == "feed one"
        assert page.locator("#feed-two").inner_text() == "feed two"
        assert page.locator("#count-one").inner_text() == "1"
        assert page.locator("body").get_attribute("data-notice") == "named payload"
        assert "named payload" not in page.locator("#stream").inner_text()
        assert page.locator(".balance-value").all_inner_texts() == ["9", "9"]
        browser.close()

    with state.lock:
        assert state.last_event_ids[:2] == [None, "5"]
        assert state.signal_requests == 1
