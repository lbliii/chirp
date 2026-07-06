"""End-to-end HEAD routing and wire contracts (#554)."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx
import pytest
from packaging.version import Version

from chirp import App, AppConfig, Fragment, Page, Request, Response
from chirp.testing import TestClient


async def _asgi_request(
    app: App,
    method: str,
    path: str,
    *,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": list(headers),
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 0),
    }
    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return start["status"], list(start["headers"]), body


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    return next((value for key, value in headers if key.lower() == name.lower()), None)


@pytest.mark.issue(554)
async def test_head_reuses_page_and_fragment_render_surfaces(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "page.html").write_text(
        "<html><body>{% block panel %}<section id=panel>{{ value }}</section>{% endblock %}</body></html>",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=templates, static_dir=None))
    seen: list[tuple[str, str]] = []

    @app.route("/page")
    def page(request: Request) -> Page:
        seen.append(("page", request.method))
        return Page("page.html", "panel", value="page value")

    @app.route("/fragment")
    def fragment(request: Request) -> Fragment:
        seen.append(("fragment", request.method))
        return Fragment("page.html", "panel", value="fragment value")

    get_status, get_headers, get_body = await _asgi_request(app, "GET", "/page")
    head_status, head_headers, head_body = await _asgi_request(app, "HEAD", "/page")
    hx_headers = ((b"hx-request", b"true"), (b"hx-target", b"panel"))
    fragment_get = await _asgi_request(app, "GET", "/fragment", headers=hx_headers)
    fragment_head = await _asgi_request(app, "HEAD", "/fragment", headers=hx_headers)

    assert get_status == head_status == 200
    assert head_body == get_body
    assert _header(head_headers, b"content-length") == _header(get_headers, b"content-length")
    assert fragment_head[0] == fragment_get[0] == 200
    assert fragment_head[2] == fragment_get[2]
    assert _header(fragment_head[1], b"content-length") == _header(
        fragment_get[1], b"content-length"
    )
    assert seen == [
        ("page", "GET"),
        ("page", "HEAD"),
        ("fragment", "GET"),
        ("fragment", "HEAD"),
    ]


@pytest.mark.issue(554)
async def test_explicit_head_handler_wins_and_allow_includes_head() -> None:
    app = App(AppConfig(static_dir=None))

    @app.route("/resource", methods=["GET"])
    def get_resource() -> Response:
        return Response("get body").with_header("X-Handler", "get")

    @app.route("/resource", methods=["HEAD"])
    def head_resource(request: Request) -> Response:
        assert request.method == "HEAD"
        return Response("head metadata").with_header("X-Handler", "head")

    async with TestClient(app) as client:
        head = await client.request("HEAD", "/resource")
        denied = await client.request("DELETE", "/resource")

    assert head.status == 200
    assert head.header("X-Handler") == "head"
    assert denied.status == 405
    assert denied.header("Allow") == "GET, HEAD"


@pytest.mark.issue(554)
async def test_head_health_and_ready_states() -> None:
    app = App(AppConfig(static_dir=None))
    app.freeze()

    health_status, health_headers, health_body = await _asgi_request(app, "HEAD", "/health")
    ready_status, ready_headers, ready_body = await _asgi_request(app, "HEAD", "/ready")

    assert health_status == 200
    assert health_body == b"ok"
    assert _header(health_headers, b"content-length") == b"2"
    assert ready_status == 503
    assert ready_body == b"not ready: starting up"
    assert _header(ready_headers, b"content-length") == str(len(ready_body)).encode()


@pytest.mark.issue(554)
async def test_pounce_082_sends_no_head_body_with_get_metadata() -> None:
    assert Version(version("bengal-pounce")) >= Version("0.8.2")
    from pounce.testing import serve

    app = App(AppConfig(static_dir=None))

    @app.route("/")
    def index() -> Response:
        return Response("dynamic head body").with_header("X-Representation", "dynamic")

    async with serve(app) as server, httpx.AsyncClient() as client:
        get_response = await client.get(server.url)
        head_response = await client.head(server.url)
        health_get = await client.get(f"{server.url}/health")
        health_head = await client.head(f"{server.url}/health")
        ready_get = await client.get(f"{server.url}/ready")
        ready_head = await client.head(f"{server.url}/ready")

    assert get_response.status_code == head_response.status_code == 200
    assert head_response.headers["content-length"] == get_response.headers["content-length"]
    assert head_response.headers["x-representation"] == "dynamic"
    assert head_response.content == b""
    assert health_get.status_code == health_head.status_code == 200
    assert health_head.headers["content-length"] == health_get.headers["content-length"]
    assert health_head.content == b""
    assert ready_get.status_code == ready_head.status_code == 200
    assert ready_head.headers["content-length"] == ready_get.headers["content-length"]
    assert ready_head.content == b""
