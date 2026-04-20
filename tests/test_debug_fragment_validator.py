"""Tests for the debug-mode fragment validator middleware."""

from __future__ import annotations

import logging

import pytest

from chirp import App, AppConfig
from chirp.http.response import Response
from chirp.middleware.debug_fragment_validator import (
    DebugFragmentValidator,
    FragmentValidationError,
)
from chirp.templating.oob_registry import OOBRegionConfig, OOBRegistry
from chirp.testing import TestClient


def _make_registry(*, with_shell: bool = True) -> OOBRegistry:
    reg = OOBRegistry()
    if with_shell:
        reg.register(
            "site_content_oob",
            OOBRegionConfig(target_id="site-content", swap="innerHTML", wrap=True),
        )
        reg.register(
            "breadcrumbs_oob",
            OOBRegionConfig(target_id="breadcrumbs", swap="innerHTML", wrap=True),
        )
    reg.freeze()
    return reg


# --- direct middleware tests ---


class TestDebugFragmentValidatorDirect:
    async def test_doctype_in_fragment_warns(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/")
        def index():
            return Response(
                body="<!DOCTYPE html><html><body>oops</body></html>",
                render_intent="fragment",
            )

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                response = await client.get("/")
        assert response.status == 200
        assert any("DOCTYPE" in rec.message for rec in caplog.records)

    async def test_duplicate_shell_id_warns(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/")
        def index():
            return Response(
                body='<div id="site-content">A</div><div id="site-content">B</div>',
                render_intent="fragment",
            )

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                response = await client.get("/")
        assert response.status == 200
        assert any('id="site-content"' in rec.message for rec in caplog.records)

    async def test_single_shell_id_no_warning(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/")
        def index():
            return Response(
                body='<div id="site-content">only one</div>',
                render_intent="fragment",
            )

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                response = await client.get("/")
        assert response.status == 200
        assert not any(
            rec.name == "chirp.middleware.debug_fragment_validator" for rec in caplog.records
        )

    async def test_full_page_intent_skipped(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/")
        def index():
            return Response(
                body="<!DOCTYPE html><html><body>page</body></html>",
                render_intent="full_page",
            )

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                response = await client.get("/")
        assert response.status == 200
        assert not any(
            rec.name == "chirp.middleware.debug_fragment_validator" for rec in caplog.records
        )

    async def test_unknown_intent_htmx_request_inspected(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/")
        def index():
            return Response(body="<!DOCTYPE html><p>hi</p>")

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                response = await client.get("/", headers={"HX-Request": "true"})
        assert response.status == 200
        assert any("DOCTYPE" in rec.message for rec in caplog.records)

    async def test_unknown_intent_non_htmx_skipped(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/")
        def index():
            return Response(body="<!DOCTYPE html><p>hi</p>")

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                response = await client.get("/")
        assert response.status == 200
        assert not any(
            rec.name == "chirp.middleware.debug_fragment_validator" for rec in caplog.records
        )

    async def test_non_html_response_skipped(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/api")
        def api():
            return Response(
                body='{"doctype": "<!DOCTYPE"}',
                content_type="application/json",
                render_intent="fragment",
            )

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                response = await client.get("/api")
        assert response.status == 200
        assert not any(
            rec.name == "chirp.middleware.debug_fragment_validator" for rec in caplog.records
        )

    async def test_strict_mode_raises(self) -> None:
        """In strict mode, a validation failure propagates as an exception.

        The app-level error handler converts it to a 500, so we assert the
        framework rendered the error rather than swallowing it silently.
        """
        app = App(AppConfig(debug=True, secret_key="dev"))
        app.add_middleware(DebugFragmentValidator(_make_registry(), strict=True))

        @app.route("/")
        def index():
            return Response(
                body="<!DOCTYPE html><p>oops</p>",
                render_intent="fragment",
            )

        async with TestClient(app) as client:
            response = await client.get("/")
        assert response.status == 500
        assert "FragmentValidationError" in response.text

    async def test_doctype_case_insensitive(self, caplog) -> None:
        app = App()
        app.add_middleware(DebugFragmentValidator(_make_registry()))

        @app.route("/")
        def index():
            return Response(
                body="<!doctype html><p>hi</p>",
                render_intent="fragment",
            )

        with caplog.at_level(logging.WARNING, "chirp.middleware.debug_fragment_validator"):
            async with TestClient(app) as client:
                await client.get("/")
        assert any("DOCTYPE" in rec.message for rec in caplog.records)


# --- auto-registration tests ---


class TestAutoRegistration:
    async def test_registered_when_debug_and_oob_regions(self) -> None:
        """Validator appears in middleware chain when debug=True and registry has regions."""
        app = App(AppConfig(debug=True, secret_key="dev"))
        app.register_oob_region(
            "site_content_oob",
            target_id="site-content",
            swap="innerHTML",
        )

        @app.route("/")
        def index():
            return "<p>ok</p>"

        async with TestClient(app):
            middleware = app._runtime_state.middleware
        assert any(isinstance(m, DebugFragmentValidator) for m in middleware)

    async def test_not_registered_when_debug_false(self) -> None:
        app = App(AppConfig(debug=False, secret_key="dev"))
        app.register_oob_region(
            "site_content_oob",
            target_id="site-content",
            swap="innerHTML",
        )

        @app.route("/")
        def index():
            return "<p>ok</p>"

        async with TestClient(app):
            middleware = app._runtime_state.middleware
        # debug=False: no debug-only middleware at all, but specifically
        # no DebugFragmentValidator.
        assert not any(isinstance(m, DebugFragmentValidator) for m in middleware)

    async def test_opt_out_via_config(self) -> None:
        app = App(
            AppConfig(
                debug=True,
                secret_key="dev",
                debug_fragment_validator=False,
            )
        )
        app.register_oob_region(
            "site_content_oob",
            target_id="site-content",
            swap="innerHTML",
        )

        @app.route("/")
        def index():
            return "<p>ok</p>"

        async with TestClient(app):
            middleware = app._runtime_state.middleware
        assert not any(isinstance(m, DebugFragmentValidator) for m in middleware)
