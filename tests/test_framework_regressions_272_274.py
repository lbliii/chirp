"""Regression tests for #272, #273, #274 — framework bugs from Lucky Cat auth work."""

from __future__ import annotations

import pytest

from chirp import App, AppConfig, Suspense
from chirp.http.request import Request
from chirp.http.response import hx_redirect
from chirp.middleware.auth import AuthConfig, AuthMiddleware, login
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.server.negotiation import negotiate
from chirp.testing import TestClient
from tests.helpers.auth import extract_session_cookie
from tests.test_auth import _USERS, _load_user


def _htmx_post_request() -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "POST",
            "path": "/login",
            "headers": [(b"hx-request", b"true")],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


def _plain_post_request() -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "POST",
            "path": "/login",
            "headers": [],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


def _auth_stack_app(*, template_dir: str) -> App:
    app = App(AppConfig(template_dir=template_dir, secret_key="test-secret", debug=False))
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    app.add_middleware(AuthMiddleware(AuthConfig(load_user=_load_user)))
    app.add_middleware(CSRFMiddleware(CSRFConfig()))
    return app


_AUTH_SUSPENSE_TEMPLATE = """\
<html><body>
{% block chrome %}
<div id="chrome">
  {% if current_user().is_authenticated %}signed-in{% else %}signed-out{% end %}
  {{ csrf_field() }}
</div>
{% end %}
{% block stats %}
<div id="stats">
  {% if stats is deferred %}pending{% else %}{{ stats }}{% end %}
</div>
{% end %}
</body></html>"""


@pytest.mark.issue(272)
class TestHxRedirectNegotiation:
    def test_htmx_strips_location_and_uses_200(self) -> None:
        response = negotiate(hx_redirect("/dashboard"), request=_htmx_post_request())
        assert response.status == 200
        assert response.header("HX-Redirect") == "/dashboard"
        assert response.header("Location") is None

    def test_non_htmx_strips_hx_redirect_keeps_location(self) -> None:
        response = negotiate(hx_redirect("/dashboard"), request=_plain_post_request())
        assert response.status == 303
        assert response.header("Location") == "/dashboard"
        assert response.header("HX-Redirect") is None


@pytest.mark.issue(273)
class TestSuspenseStreamingAuthCsrfContext:
    @pytest.mark.asyncio
    async def test_shell_keeps_auth_and_csrf_after_middleware_reset(self, tmp_path) -> None:
        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "panel.html").write_text(_AUTH_SUSPENSE_TEMPLATE)

        app = _auth_stack_app(template_dir=str(templates))

        @app.route("/do-login")
        def do_login():
            login(_USERS["1"])
            return "ok"

        async def load_stats():
            return "ready"

        @app.route("/panel")
        async def panel():
            return Suspense("panel.html", stats=load_stats())

        async with TestClient(app) as client:
            login_resp = await client.get("/do-login")
            cookie = extract_session_cookie(login_resp, "chirp_session")
            response = await client.get("/panel", headers={"Cookie": f"chirp_session={cookie}"})
            assert response.status == 200
            assert "signed-in" in response.text
            assert 'name="_csrf_token"' in response.text
            assert "ready" in response.text


@pytest.mark.issue(274)
class TestRouteMetaAuthEnforcement:
    @pytest.mark.asyncio
    async def test_meta_auth_required_redirects_anonymous(self, tmp_path) -> None:
        pages = tmp_path / "pages"
        protected = pages / "account"
        protected.mkdir(parents=True)
        (protected / "_meta.py").write_text(
            """
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Account", auth="required")
"""
        )
        (protected / "page.py").write_text(
            """
def get():
    return "ok"
"""
        )
        (protected / "page.html").write_text("<p>secret</p>")

        app = _auth_stack_app(template_dir=str(pages))
        app.mount_pages(str(pages))

        async with TestClient(app) as client:
            response = await client.get("/account")
            assert response.status == 302
            assert "/login" in response.header("Location", "")

    @pytest.mark.asyncio
    async def test_meta_auth_required_allows_signed_in(self, tmp_path) -> None:
        pages = tmp_path / "pages"
        protected = pages / "account"
        protected.mkdir(parents=True)
        (protected / "_meta.py").write_text(
            """
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Account", auth="required")
"""
        )
        (protected / "page.py").write_text(
            """
def get():
    return "secret"
"""
        )
        (protected / "page.html").write_text(
            "{% block page_root %}{% block content %}<p>secret</p>{% end %}{% end %}"
        )

        app = _auth_stack_app(template_dir=str(pages))

        @app.route("/do-login")
        def do_login():
            login(_USERS["1"])
            return "ok"

        app.mount_pages(str(pages))

        async with TestClient(app) as client:
            login_resp = await client.get("/do-login")
            cookie = extract_session_cookie(login_resp, "chirp_session")
            response = await client.get(
                "/account",
                headers={"Cookie": f"chirp_session={cookie}"},
            )
            assert response.status == 200
            assert "secret" in response.text
