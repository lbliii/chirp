"""Boundary integration tests: Chirp ↔ ChirpUI.

Determines whether failures originate in Chirp (the framework) or
ChirpUI (the UI library) by testing each layer in isolation, then
testing them together.

Structure:
    A — Chirp-only (no ChirpUI): proves framework handles API patterns correctly
    B — ChirpUI integration: proves use_chirp_ui doesn't break anything
    C — HTML contract: proves rendered pages have correct interactivity attributes
    D — Middleware stacking: proves ChirpUI middleware doesn't interfere with
        ContextVars, SSE, or outbound HTTP

If A passes and B fails → ChirpUI broke it.
If A fails → Chirp's fault, ChirpUI is irrelevant.
If both pass → issue is in app code or external services, not framework.
"""

import contextvars
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

chirp_ui = pytest.importorskip("chirp_ui", reason="chirp-ui not installed")

from chirp import App, AppConfig, EventStream, Fragment, Request, Response, SSEEvent, Template
from chirp.ext.chirp_ui import use_chirp_ui
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Shared ContextVar (simulates the httpx client pattern in all AI examples)
# ---------------------------------------------------------------------------

_api_client_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "boundary_test_client", default=None
)

TEMPLATES_DIR = Path(__file__).parent / "templates" / "boundary"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chirp_only_app() -> App:
    """Minimal Chirp app WITHOUT ChirpUI — framework only."""
    config = AppConfig(template_dir=TEMPLATES_DIR)
    app = App(config=config)

    @app.on_worker_startup
    async def startup():
        _api_client_var.set("chirp-only-client")

    @app.on_worker_shutdown
    async def shutdown():
        _api_client_var.set(None)

    @app.route("/")
    def index():
        value = _api_client_var.get()
        return Response(body=json.dumps({"client": value}), content_type="application/json")

    @app.route("/api/check")
    def api_check():
        value = _api_client_var.get()
        body = json.dumps({"contextvar": value, "source": "chirp-only"})
        return Response(body=body, content_type="application/json")

    @app.route("/chat", methods=["POST"])
    async def post_chat(request: Request):
        form = await request.form()
        message = form.get("message", "")
        value = _api_client_var.get()
        body = json.dumps({
            "message": message,
            "contextvar": value,
            "source": "chirp-only",
        })
        return Response(body=body, content_type="application/json")

    @app.route("/stream")
    def stream():
        async def generate():
            value = _api_client_var.get()
            for i in range(3):
                yield SSEEvent(
                    event="token",
                    data=json.dumps({"idx": i, "client": value}),
                )
            yield SSEEvent(event="done", data="complete")

        return EventStream(generate())

    return app


def _make_chirpui_app() -> App:
    """Chirp app WITH ChirpUI — tests the integration boundary."""
    config = AppConfig(template_dir=TEMPLATES_DIR)
    app = App(config=config)
    use_chirp_ui(app)

    @app.on_worker_startup
    async def startup():
        _api_client_var.set("chirpui-client")

    @app.on_worker_shutdown
    async def shutdown():
        _api_client_var.set(None)

    @app.route("/")
    def index():
        return Template("chirpui_index.html", client_value=_api_client_var.get())

    @app.route("/api/check")
    def api_check():
        value = _api_client_var.get()
        body = json.dumps({"contextvar": value, "source": "chirpui"})
        return Response(body=body, content_type="application/json")

    @app.route("/chat", methods=["POST"])
    async def post_chat(request: Request):
        form = await request.form()
        message = form.get("message", "")
        value = _api_client_var.get()
        return Fragment(
            "chirpui_index.html",
            "chat_response",
            message=message,
            contextvar=value,
        )

    @app.route("/stream")
    def stream():
        async def generate():
            value = _api_client_var.get()
            for i in range(3):
                yield SSEEvent(
                    event="fragment",
                    data=f'<span class="token">{i}:{value}</span>',
                )
            yield SSEEvent(event="done", data="complete")

        return EventStream(generate())

    @app.route("/static-check")
    def static_check():
        value = _api_client_var.get()
        return Template("chirpui_index.html", client_value=value)

    return app


# ===========================================================================
# A — Chirp-only tests (no ChirpUI)
# ===========================================================================


class TestChirpOnly:
    """Framework-only tests — if these fail, it's Chirp's fault."""

    async def test_contextvar_set_in_worker_startup(self):
        """Worker startup hook runs and sets ContextVar."""
        app = _make_chirp_only_app()
        async with TestClient(app) as client:
            resp = await client.get("/api/check")
            data = json.loads(resp.text)
            assert data["contextvar"] == "chirp-only-client"

    async def test_contextvar_visible_in_post_handler(self):
        """POST handler reads ContextVar set in worker startup."""
        app = _make_chirp_only_app()
        async with TestClient(app) as client:
            resp = await client.post(
                "/chat",
                data={"message": "hello"},
            )
            data = json.loads(resp.text)
            assert data["contextvar"] == "chirp-only-client", (
                f"Chirp POST handler lost ContextVar: {data}"
            )
            assert data["message"] == "hello"

    async def test_contextvar_visible_in_sse_generator(self):
        """SSE generator reads ContextVar set in worker startup."""
        app = _make_chirp_only_app()
        async with TestClient(app) as client:
            result = await client.sse("/stream", max_events=5)
            assert result.status == 200
            token_events = [e for e in result.events if e.event == "token"]
            assert len(token_events) >= 1
            data = json.loads(token_events[0].data)
            assert data["client"] == "chirp-only-client", (
                f"Chirp SSE generator lost ContextVar: {data}"
            )

    async def test_contextvar_stable_across_requests(self):
        """Multiple sequential requests all see the same ContextVar."""
        app = _make_chirp_only_app()
        async with TestClient(app) as client:
            for i in range(5):
                resp = await client.get("/api/check")
                data = json.loads(resp.text)
                assert data["contextvar"] == "chirp-only-client", (
                    f"Request {i}: ContextVar was {data['contextvar']!r}"
                )


# ===========================================================================
# B — ChirpUI integration tests
# ===========================================================================


class TestChirpUIIntegration:
    """Tests with use_chirp_ui(app) active — if A passes and B fails,
    ChirpUI broke it."""

    async def test_contextvar_survives_chirpui_middleware(self):
        """ContextVar set in worker startup is visible through ChirpUI middleware."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/api/check")
            data = json.loads(resp.text)
            assert data["contextvar"] == "chirpui-client", (
                f"ChirpUI middleware broke ContextVar: {data}"
            )

    async def test_post_through_chirpui_middleware(self):
        """POST request works through ChirpUI middleware stack."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.post(
                "/chat",
                data={"message": "test"},
            )
            assert resp.status == 200
            assert "test" in resp.text

    async def test_sse_through_chirpui_middleware(self):
        """SSE streaming works through ChirpUI middleware stack."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            result = await client.sse("/stream", max_events=5)
            assert result.status == 200
            fragment_events = [e for e in result.events if e.event == "fragment"]
            assert len(fragment_events) >= 1
            assert "chirpui-client" in fragment_events[0].data, (
                f"SSE through ChirpUI lost ContextVar: {fragment_events[0].data}"
            )

    async def test_static_css_served(self):
        """ChirpUI CSS is served at /static/chirpui.css."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/static/chirpui.css")
            assert resp.status == 200
            assert "chirpui" in resp.text.lower() or len(resp.text) > 100

    async def test_static_js_served(self):
        """ChirpUI JS is served at /static/chirpui.js."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/static/chirpui.js")
            assert resp.status == 200

    async def test_sequential_requests_through_middleware(self):
        """Multiple requests through ChirpUI middleware all see ContextVar."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            for i in range(5):
                resp = await client.get("/api/check")
                data = json.loads(resp.text)
                assert data["contextvar"] == "chirpui-client", (
                    f"Request {i} through ChirpUI: {data}"
                )


# ===========================================================================
# C — HTML contract tests (rendered output has correct interactivity attrs)
# ===========================================================================


class TestHTMLContract:
    """Verify rendered HTML has the attributes browsers need for interactivity.

    If these fail, the page looks fine but htmx/SSE won't fire — causing
    the exact 'silently broken' symptom.
    """

    async def test_page_includes_htmx_script(self):
        """Rendered page has an htmx script tag."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
            assert resp.status == 200
            html = resp.text
            assert "htmx.org" in html or "htmx.min.js" in html, (
                "Page is missing htmx script tag — forms won't submit via AJAX"
            )

    async def test_page_includes_sse_extension(self):
        """Rendered page has the htmx SSE extension script."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
            html = resp.text
            assert "sse.js" in html or "htmx-ext-sse" in html, (
                "Page is missing htmx-ext-sse — SSE streaming won't work"
            )

    async def test_form_has_hx_post(self):
        """Chat form has hx-post attribute pointing to the right endpoint."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
            html = resp.text
            assert 'hx-post="/chat"' in html, (
                "Chat form is missing hx-post='/chat' — form submission won't use htmx"
            )

    async def test_form_has_hx_target(self):
        """Chat form has hx-target so response goes to the right element."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
            html = resp.text
            assert "hx-target=" in html, (
                "Chat form is missing hx-target — response will replace entire page"
            )

    async def test_sse_div_has_sse_connect(self):
        """Activity panel has sse-connect attribute for live updates."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
            html = resp.text
            assert "sse-connect=" in html, (
                "No sse-connect attribute found — SSE live updates won't connect"
            )

    async def test_chirpui_css_link_present(self):
        """Page includes a link to chirpui.css."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
            html = resp.text
            assert "chirpui.css" in html, (
                "Page is missing chirpui.css link — components will be unstyled"
            )

    async def test_no_duplicate_htmx_scripts(self):
        """Page should not load htmx twice (causes double-processing)."""
        app = _make_chirpui_app()
        async with TestClient(app) as client:
            resp = await client.get("/")
            html = resp.text
            count = html.count("htmx.org")
            assert count <= 1, (
                f"htmx loaded {count} times — duplicate scripts cause silent double-processing"
            )


# ===========================================================================
# D — Comparative A/B tests (same app, with and without ChirpUI)
# ===========================================================================


class TestComparativeAB:
    """Run the same operation with and without ChirpUI to find the break point.

    Each test does the same thing twice: once through a bare Chirp app,
    once through a ChirpUI-enabled app. If one fails and the other passes,
    we know which layer is responsible.
    """

    async def test_post_contextvar_chirp_vs_chirpui(self):
        """POST ContextVar: compare bare Chirp vs ChirpUI-enabled."""
        # Chirp only
        bare = _make_chirp_only_app()
        async with TestClient(bare) as client:
            resp = await client.post("/chat", data={"message": "test"})
            bare_data = json.loads(resp.text)

        # With ChirpUI
        ui = _make_chirpui_app()
        async with TestClient(ui) as client:
            resp = await client.get("/api/check")
            ui_data = json.loads(resp.text)

        assert bare_data["contextvar"] is not None, "CHIRP: ContextVar lost in POST"
        assert ui_data["contextvar"] is not None, "CHIRPUI: ContextVar lost after middleware"

    async def test_sse_chirp_vs_chirpui(self):
        """SSE streaming: compare bare Chirp vs ChirpUI-enabled."""
        # Chirp only
        bare = _make_chirp_only_app()
        async with TestClient(bare) as client:
            bare_result = await client.sse("/stream", max_events=5)

        # With ChirpUI
        ui = _make_chirpui_app()
        async with TestClient(ui) as client:
            ui_result = await client.sse("/stream", max_events=5)

        bare_tokens = [e for e in bare_result.events if e.event == "token"]
        ui_fragments = [e for e in ui_result.events if e.event == "fragment"]

        assert len(bare_tokens) >= 1, "CHIRP: SSE produced no events"
        assert len(ui_fragments) >= 1, "CHIRPUI: SSE produced no events through middleware"

        bare_data = json.loads(bare_tokens[0].data)
        assert bare_data["client"] is not None, "CHIRP: SSE lost ContextVar"
        assert "chirpui-client" in ui_fragments[0].data, "CHIRPUI: SSE lost ContextVar"

    async def test_worker_startup_chirp_vs_chirpui(self):
        """Worker startup hooks: compare bare Chirp vs ChirpUI-enabled."""
        bare = _make_chirp_only_app()
        async with TestClient(bare) as client:
            resp = await client.get("/api/check")
            bare_data = json.loads(resp.text)

        ui = _make_chirpui_app()
        async with TestClient(ui) as client:
            resp = await client.get("/api/check")
            ui_data = json.loads(resp.text)

        assert bare_data["contextvar"] == "chirp-only-client", (
            f"CHIRP worker startup failed: {bare_data}"
        )
        assert ui_data["contextvar"] == "chirpui-client", (
            f"CHIRPUI worker startup failed: {ui_data}"
        )
