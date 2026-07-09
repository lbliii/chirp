"""Nonce-safe conditional response regression coverage for issue #659."""

from __future__ import annotations

import re

import pytest

from chirp import App, AppConfig, Response
from chirp.cache.backends.memory import MemoryCacheBackend
from chirp.cache.middleware import CacheMiddleware
from chirp.middleware.csp_nonce import CSPNonceMiddleware
from chirp.middleware.inject import HTMLInject
from chirp.middleware.static import StaticFiles
from chirp.testing import TestClient

_ETAG = '"page-v1"'
_LAST_MODIFIED = "Sun, 06 Nov 1994 08:49:37 GMT"


def _header(response, name: str) -> str | None:
    return response.header(name)


def _nonce(response) -> str:
    csp = _header(response, "Content-Security-Policy")
    assert csp is not None
    match = re.search(r"'nonce-([^']+)'", csp)
    assert match is not None
    return match.group(1)


def _assert_all_inline_scripts_match_csp(response) -> None:
    nonces = re.findall(r'<script nonce="([^"]+)">', response.text)
    assert nonces
    assert set(nonces) == {_nonce(response)}


def _route_validator_app(*, content_type: str = "text/html", csp: bool = True) -> App:
    app = App(AppConfig(csp_nonce_enabled=csp))

    @app.route(
        "/",
        methods=["GET", "QUERY"],
        query_media_types=("application/x-www-form-urlencoded",),
    )
    def page() -> Response:
        return Response(
            "<html><body><script>boot()</script><script>hydrate()</script></body></html>",
            content_type=content_type,
        ).with_header("ETag", _ETAG)

    return app


@pytest.mark.issue(659)
@pytest.mark.parametrize("method", ["GET", "HEAD", "QUERY"])
async def test_nonce_html_etag_always_returns_a_fresh_representation(method: str) -> None:
    app = _route_validator_app()
    base_headers = (
        {"Content-Type": "application/x-www-form-urlencoded"} if method == "QUERY" else {}
    )

    async with TestClient(app) as client:
        first = await client.request(method, "/", headers=base_headers, body=b"q=first")
        second = await client.request(
            method,
            "/",
            headers={**base_headers, "If-None-Match": _ETAG},
            body=b"q=second",
        )

    assert first.status == 200
    assert second.status == 200
    assert _nonce(first) != _nonce(second)
    if method != "HEAD":
        _assert_all_inline_scripts_match_csp(second)


@pytest.mark.issue(659)
async def test_nonce_html_last_modified_always_returns_a_fresh_representation() -> None:
    app = App(AppConfig(csp_nonce_enabled=True))

    @app.route("/")
    def page() -> Response:
        return Response("<script>boot()</script>").with_header("Last-Modified", _LAST_MODIFIED)

    async with TestClient(app) as client:
        first = await client.get("/")
        second = await client.get("/", headers={"If-Modified-Since": _LAST_MODIFIED})

    assert second.status == 200
    assert _nonce(first) != _nonce(second)
    assert f'<script nonce="{_nonce(second)}">boot()</script>' in second.text


class _ValidatorMiddleware:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value

    async def __call__(self, request, next):
        response = await next(request)
        assert isinstance(response, Response)
        return response.with_header(self.name, self.value)


@pytest.mark.issue(659)
@pytest.mark.parametrize(
    ("validator_name", "validator_value", "request_header"),
    [
        ("ETag", _ETAG, ("If-None-Match", _ETAG)),
        ("Last-Modified", _LAST_MODIFIED, ("If-Modified-Since", _LAST_MODIFIED)),
    ],
)
async def test_middleware_validators_cannot_bypass_nonce_safety(
    validator_name: str,
    validator_value: str,
    request_header: tuple[str, str],
) -> None:
    app = App()
    app.add_middleware(_ValidatorMiddleware(validator_name, validator_value))
    app.add_middleware(CSPNonceMiddleware())

    @app.route("/")
    def page() -> Response:
        return Response("<script>boot()</script>")

    async with TestClient(app) as client:
        first = await client.get("/")
        second = await client.get("/", headers={request_header[0]: request_header[1]})

    assert second.status == 200
    assert _nonce(first) != _nonce(second)
    assert f'<script nonce="{_nonce(second)}">boot()</script>' in second.text


@pytest.mark.issue(659)
@pytest.mark.parametrize(
    ("content_type", "csp"),
    [
        ("application/json", True),
        ("text/markdown; charset=utf-8", True),
        ("text/html; charset=utf-8", False),
    ],
)
async def test_stable_representations_keep_conditional_304(
    content_type: str,
    csp: bool,
) -> None:
    app = _route_validator_app(content_type=content_type, csp=csp)

    async with TestClient(app) as client:
        response = await client.get("/", headers={"If-None-Match": _ETAG})

    assert response.status == 304
    assert response.body == b""


@pytest.mark.issue(659)
async def test_stable_middleware_validator_is_evaluated_after_the_chain() -> None:
    app = App(AppConfig(csp_nonce_enabled=True))
    app.add_middleware(_ValidatorMiddleware("ETag", _ETAG))

    @app.route("/")
    def data() -> Response:
        return Response("{}", content_type="application/json")

    async with TestClient(app) as client:
        response = await client.get("/", headers={"If-None-Match": _ETAG})

    assert response.status == 304


@pytest.mark.issue(659)
async def test_nonce_html_bypasses_shared_response_cache() -> None:
    app = App(AppConfig(csp_nonce_enabled=True))
    backend = MemoryCacheBackend()
    app.add_middleware(CacheMiddleware(backend))
    calls = 0

    @app.route("/")
    def page() -> Response:
        nonlocal calls
        calls += 1
        return Response(f"<script>boot({calls})</script>").with_header("ETag", _ETAG)

    async with TestClient(app) as client:
        first = await client.get("/")
        second = await client.get("/", headers={"If-None-Match": _ETAG})

    assert first.status == second.status == 200
    assert calls == 2
    assert backend._store == {}
    assert _nonce(first) != _nonce(second)
    assert "boot(2)" in second.text


@pytest.mark.issue(659)
async def test_injected_static_inline_script_does_not_short_circuit_before_csp(
    tmp_path,
) -> None:
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text("<html><body><script>boot()</script></body></html>")
    app = App()
    app.add_middleware(CSPNonceMiddleware())
    app.add_middleware(HTMLInject("<!-- stable injection -->"))
    app.add_middleware(StaticFiles(directory=public, prefix="/"))

    async with TestClient(app) as client:
        first = await client.get("/")
        etag = _header(first, "ETag")
        assert etag is not None
        second = await client.get("/", headers={"If-None-Match": etag})

    assert second.status == 200
    assert _nonce(first) != _nonce(second)
    assert f'<script nonce="{_nonce(second)}">boot()</script>' in second.text
