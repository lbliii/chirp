"""Opt-in browser proof for the htmx 4 trigger-header migration (#549).

Run against exact upstream checkouts so the normal suite stays offline::

    git clone --depth 1 --branch v2.0.10 \
      https://github.com/bigskysoftware/htmx.git /tmp/htmx-2.0.10
    git clone --depth 1 --branch v4.0.0-beta5 \
      https://github.com/bigskysoftware/htmx.git /tmp/htmx-4.0.0-beta5
    CHIRP_HTMX4_TRIGGER_SPIKE=1 \
    HTMX2_SOURCE_ROOT=/tmp/htmx-2.0.10 \
    HTMX4_SOURCE_ROOT=/tmp/htmx-4.0.0-beta5 \
      uv run pytest tests/spikes/test_htmx4_trigger_headers_preview.py -q
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HTMX2_COMMIT = "bdc7d7d3e25d0390c7ee11049806e8279b075598"
HTMX2_SHA256 = "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de"
HTMX4_COMMIT = "5300af9e7af8b196f9fbf806cab79a5780b62291"
HTMX4_SHA256 = "192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68"


def _page(version: int) -> bytes:
    lifecycle = (
        ("htmx:afterSwap", "htmx:afterSettle")
        if version == 2
        else ("htmx:after:swap", "htmx:after:settle")
    )
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><script src="/v{version}/htmx.min.js"></script></head>
  <body>
    <button id="load" hx-get="/swap" hx-target="#output" hx-swap="innerHTML settle:80ms">
      Load
    </button>
    <div id="output">before</div>
    <script>
      window.proof = [];
      function record(name, event) {{
        window.proof.push({{
          name,
          output: document.getElementById("output").textContent.trim(),
          detail: event.detail && event.detail.phase
        }});
      }}
      for (const name of ["received", "after-swap", "after-settle"]) {{
        document.body.addEventListener(name, (event) => record(name, event));
      }}
      document.body.addEventListener("{lifecycle[0]}", (event) => record("core-after-swap", event));
      document.body.addEventListener("{lifecycle[1]}", (event) => record("core-after-settle", event));
    </script>
  </body>
</html>
""".encode()


@dataclass(slots=True)
class _Assets:
    htmx2: bytes
    htmx4: bytes


class _Server(ThreadingHTTPServer):
    assets: _Assets


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        if self.path == "/v2":
            self._send(_page(2), "text/html; charset=utf-8")
            return
        if self.path == "/v4":
            self._send(_page(4), "text/html; charset=utf-8")
            return
        if self.path == "/v2/htmx.min.js":
            self._send(self.server.assets.htmx2, "text/javascript; charset=utf-8")
            return
        if self.path == "/v4/htmx.min.js":
            self._send(self.server.assets.htmx4, "text/javascript; charset=utf-8")
            return
        if self.path == "/swap":
            body = b'<strong id="replacement">after</strong>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("HX-Trigger", json.dumps({"received": {"phase": "receipt"}}))
            self.send_header("HX-Trigger-After-Swap", json.dumps({"after-swap": {"phase": "swap"}}))
            self.send_header(
                "HX-Trigger-After-Settle", json.dumps({"after-settle": {"phase": "settle"}})
            )
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def _serve(assets: _Assets):
    server = _Server(("127.0.0.1", 0), _Handler)
    server.assets = assets
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _asset(env_name: str, relative: str, expected_sha256: str) -> Path:
    source_root = os.environ.get(env_name)
    if not source_root:
        pytest.fail(f"{env_name} must point to the pinned htmx checkout")
    path = Path(source_root) / relative
    assert _sha256(path) == expected_sha256
    return path


@pytest.mark.issue(549)
@pytest.mark.integration
def test_removed_trigger_headers_cannot_be_losslessly_remapped() -> None:
    if os.environ.get("CHIRP_HTMX4_TRIGGER_SPIKE") != "1":
        pytest.skip("set CHIRP_HTMX4_TRIGGER_SPIKE=1 to run the pinned browser spike")

    htmx2_path = _asset("HTMX2_SOURCE_ROOT", "dist/htmx.min.js", HTMX2_SHA256)
    htmx4_path = _asset("HTMX4_SOURCE_ROOT", "dist/htmx.min.js", HTMX4_SHA256)

    from playwright.sync_api import sync_playwright

    assets = _Assets(htmx2=htmx2_path.read_bytes(), htmx4=htmx4_path.read_bytes())
    with _serve(assets) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        proofs: dict[int, list[dict[str, object]]] = {}
        for version in (2, 4):
            page = browser.new_page()
            page.goto(f"{base_url}/v{version}")
            page.locator("#load").click()
            page.locator("#replacement").wait_for(timeout=10_000)
            page.wait_for_timeout(150)
            proofs[version] = page.evaluate("window.proof")
            page.close()
        browser.close()

    v2_names = [entry["name"] for entry in proofs[2]]
    assert v2_names.index("received") < v2_names.index("after-swap")
    assert v2_names.index("after-swap") < v2_names.index("after-settle")
    assert next(entry for entry in proofs[2] if entry["name"] == "received")["output"] == "before"
    assert next(entry for entry in proofs[2] if entry["name"] == "after-swap")["output"] == "after"
    assert (
        next(entry for entry in proofs[2] if entry["name"] == "after-settle")["output"] == "after"
    )

    v4_names = [entry["name"] for entry in proofs[4]]
    assert "received" in v4_names
    assert "after-swap" not in v4_names
    assert "after-settle" not in v4_names
    assert v4_names.index("core-after-settle") < v4_names.index("core-after-swap")
