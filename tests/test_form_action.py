"""Tests for FormAction — progressive enhancement for form submissions."""

from pathlib import Path

from chirp.app import App
from chirp.config import AppConfig
from chirp.templating.returns import FormAction, Fragment
from chirp.testing import TestClient

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _app(**overrides: object) -> App:
    """Build an app wired to the test templates directory."""
    cfg = AppConfig(template_dir=TEMPLATES_DIR, **overrides)
    return App(config=cfg)


# ---------------------------------------------------------------------------
# Unit tests — FormAction construction
# ---------------------------------------------------------------------------


class TestFormActionConstruction:
    def test_redirect_only(self) -> None:
        fa = FormAction("/contacts")
        assert fa.redirect == "/contacts"
        assert fa.fragments == ()
        assert fa.trigger is None
        assert fa.status == 303

    def test_with_fragments(self) -> None:
        f1 = Fragment("search.html", "results_list", results=[])
        f2 = Fragment("cart.html", "counter", count=5)
        fa = FormAction("/ok", f1, f2)
        assert fa.fragments == (f1, f2)

    def test_with_trigger(self) -> None:
        fa = FormAction("/x", trigger="saved")
        assert fa.trigger == "saved"

    def test_custom_status(self) -> None:
        fa = FormAction("/x", status=301)
        assert fa.status == 301


# ---------------------------------------------------------------------------
# Integration tests — non-htmx (standard browser POST)
# ---------------------------------------------------------------------------


def _header(response, name: str) -> str | None:
    """Get a header value from the test response (list of tuples)."""
    for hname, hvalue in response.headers:
        if hname == name:
            return hvalue
    return None


class TestFormActionNonHtmx:
    async def test_redirects_with_303(self) -> None:
        """Non-htmx POST returns 303 redirect."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction("/thanks")

        async with TestClient(app) as client:
            response = await client.post("/submit")

        assert response.status == 303
        assert _header(response, "location") == "/thanks"

    async def test_custom_status_code(self) -> None:
        """Non-htmx redirect uses custom status code."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction("/moved", status=301)

        async with TestClient(app) as client:
            response = await client.post("/submit")

        assert response.status == 301
        assert _header(response, "location") == "/moved"

    async def test_fragments_ignored_for_non_htmx(self) -> None:
        """Non-htmx always gets redirect, even when fragments are provided."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=["a"]),
                trigger="added",
            )

        async with TestClient(app) as client:
            response = await client.post("/submit")

        assert response.status == 303
        assert _header(response, "location") == "/contacts"


# ---------------------------------------------------------------------------
# Integration tests — htmx (fragment requests)
# ---------------------------------------------------------------------------


class TestFormActionHtmx:
    async def test_no_fragments_sends_hx_redirect(self) -> None:
        """htmx POST with no fragments sends HX-Redirect header."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction("/dashboard")

        async with TestClient(app) as client:
            response = await client.post(
                "/submit", headers={"HX-Request": "true"},
            )

        assert response.status == 200
        assert _header(response, "hx-redirect") == "/dashboard"

    async def test_with_fragments_renders_html(self) -> None:
        """htmx POST with fragments renders the fragment HTML."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=["alpha", "beta"]),
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/submit", headers={"HX-Request": "true"},
            )

        assert response.status == 200
        assert "alpha" in response.text
        assert "beta" in response.text
        # No redirect header — fragments were rendered instead
        assert _header(response, "hx-redirect") is None

    async def test_trigger_header_present(self) -> None:
        """HX-Trigger header is set when trigger is specified."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=[]),
                trigger="contactAdded",
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/submit", headers={"HX-Request": "true"},
            )

        assert _header(response, "hx-trigger") == "contactAdded"

    async def test_no_trigger_header_when_not_set(self) -> None:
        """HX-Trigger header is absent when trigger is None."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction(
                "/contacts",
                Fragment("search.html", "results_list", results=[]),
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/submit", headers={"HX-Request": "true"},
            )

        assert _header(response, "hx-trigger") is None

    async def test_multiple_fragments(self) -> None:
        """Multiple fragments are rendered in the response body."""
        app = _app()

        @app.route("/submit", methods=["POST"])
        def submit():
            return FormAction(
                "/ok",
                Fragment("search.html", "results_list", results=["x"]),
                Fragment("cart.html", "counter", count=42),
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/submit", headers={"HX-Request": "true"},
            )

        assert response.status == 200
        # Both fragments rendered
        assert "x" in response.text
        assert "42" in response.text
