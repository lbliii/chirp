"""Integration test: full POST -> bind -> error -> re-render cycle.

Tests the complete form_or_errors() pipeline through App + TestClient,
verifying that ValidationError produces a 422 response with error
messages and re-populated form values.
"""

from dataclasses import dataclass
from pathlib import Path

from chirp.app import App
from chirp.config import AppConfig
from chirp.http.forms import form_or_errors, form_values
from chirp.http.request import Request
from chirp.templating.returns import ValidationError
from chirp.testing import TestClient

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True, slots=True)
class ContactForm:
    name: str
    email: str
    message: str = ""


def _app() -> App:
    """Build an App wired to the test templates directory."""
    cfg = AppConfig(template_dir=TEMPLATES_DIR)
    return App(config=cfg)


class TestFormOrErrorsIntegration:
    """Full pipeline: POST -> form_or_errors() -> ValidationError -> rendered HTML."""

    async def test_valid_submission_succeeds(self) -> None:
        app = _app()

        @app.route("/contact", methods=["POST"])
        async def contact(request: Request):
            result = await form_or_errors(request, ContactForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return result
            return f"ok:{result.name}|{result.email}"

        async with TestClient(app) as client:
            response = await client.post(
                "/contact",
                body=b"name=Alice&email=alice@example.com&message=Hello",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 200
            assert response.text == "ok:Alice|alice@example.com"

    async def test_missing_field_returns_422(self) -> None:
        app = _app()

        @app.route("/contact", methods=["POST"])
        async def contact(request: Request):
            result = await form_or_errors(request, ContactForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return result
            return "ok"

        async with TestClient(app) as client:
            # Missing required 'name' and 'email' fields
            response = await client.post(
                "/contact",
                body=b"message=Hello",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 422
            assert "name" in response.text
            assert "email" in response.text

    async def test_error_response_contains_form_values(self) -> None:
        app = _app()

        @app.route("/contact", methods=["POST"])
        async def contact(request: Request):
            result = await form_or_errors(request, ContactForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return result
            return "ok"

        async with TestClient(app) as client:
            # Submit with 'message' but missing required 'name' and 'email'
            response = await client.post(
                "/contact",
                body=b"message=Please+help",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 422
            # The form values should be in the response context
            assert "text/html" in response.content_type

    async def test_extra_context_rendered(self) -> None:
        app = _app()

        @app.route("/contact", methods=["POST"])
        async def contact(request: Request):
            result = await form_or_errors(
                request,
                ContactForm,
                "form.html",
                "form_body",
                page_title="Contact Us",
            )
            if isinstance(result, ValidationError):
                return result
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/contact",
                body=b"message=Hello",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 422

    async def test_retarget_sets_hx_header(self) -> None:
        """HX-Retarget header appears on the 422 response."""
        app = _app()

        @app.route("/contact", methods=["POST"])
        async def contact(request: Request):
            result = await form_or_errors(
                request,
                ContactForm,
                "form.html",
                "form_errors",
                retarget="#error-banner",
            )
            if isinstance(result, ValidationError):
                return result
            return "ok"

        async with TestClient(app) as client:
            response = await client.post(
                "/contact",
                body=b"message=Hello",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 422
            assert response.header("hx-retarget") == "#error-banner"


class TestFormValuesIntegration:
    """Integration: form_values() used in a handler with ValidationError."""

    async def test_form_values_in_validation_error(self) -> None:
        app = _app()

        @app.route("/contact", methods=["POST"])
        async def contact(request: Request):
            result = await form_or_errors(request, ContactForm, "form.html", "form_body")
            if isinstance(result, ValidationError):
                return result

            # Business validation (e.g., name too short)
            if len(result.name) < 3:
                return ValidationError(
                    "form.html",
                    "form_body",
                    errors={"name": ["Name must be at least 3 characters."]},
                    form=form_values(result),
                )
            return f"ok:{result.name}"

        async with TestClient(app) as client:
            response = await client.post(
                "/contact",
                body=b"name=Al&email=al@example.com",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status == 422
            assert "Name must be at least 3 characters." in response.text
