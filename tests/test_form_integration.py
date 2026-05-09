"""Integration test: full POST -> bind -> error -> re-render cycle.

Tests the complete form_or_errors() pipeline through App + TestClient,
verifying that ValidationError produces a 422 response with error
messages and re-populated form values.
"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.http.forms import form_or_errors, form_values
from chirp.http.request import Request
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.templating.returns import ValidationError
from chirp.testing import TestClient
from tests.helpers.auth import extract_csrf_token, extract_session_cookie

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


def _write_product_form_pages(pages_dir: Path) -> None:
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        "<html><body><main>{% block page_root %}{% block content %}{% end %}{% end %}</main></body></html>"
    )
    (pages_dir / "page.py").write_text(
        """
from dataclasses import dataclass

from chirp import Page, Request, ValidationError, form_from
from chirp.contracts import FormContract, contract
from chirp.http.forms import FormBindingError


@dataclass(frozen=True, slots=True)
class ProductForm:
    title: str
    tags: list[str]
    intent: str


def get():
    return Page("page.html", "content", page_block_name="page_root", form={}, errors={})


@contract(form=FormContract(ProductForm, "page.html", "content"))
async def post(request: Request):
    try:
        form = await form_from(request, ProductForm)
    except FormBindingError as exc:
        return ValidationError("page.html", "content", errors=exc.errors, form={})

    if form.intent not in {"save", "publish"}:
        return ValidationError(
            "page.html",
            "content",
            errors={"intent": ["Unknown action"]},
            form={"title": form.title, "tags": form.tags, "intent": form.intent},
            retarget="#composer",
        )

    return f"{form.intent}:{form.title}:{','.join(form.tags)}"
"""
    )
    (pages_dir / "page.html").write_text(
        """
{% block page_root %}{% block content %}
<form id="composer" method="post" action="/">
  {{ csrf_field() }}
  <label>Title <input name="title" value="{{ form.title | default('') }}"></label>
  <label>Docs <input type="checkbox" name="tags" value="docs"></label>
  <label>Bug <input type="checkbox" name="tags" value="bug"></label>
  <input type="submit" name="intent" value="save">
  <input type="submit" name="intent" value="publish">
  {% if errors %}
  <ul class="errors">
    {% for field, msgs in errors.items() %}
      {% for msg in msgs %}
      <li>{{ field }}: {{ msg }}</li>
      {% endfor %}
    {% endfor %}
  </ul>
  {% endif %}
</form>
{% end %}{% end %}
"""
    )


def _product_form_app(pages_dir: Path) -> App:
    app = App(AppConfig(template_dir=str(pages_dir), debug=False))
    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="test-secret")))
    app.add_middleware(CSRFMiddleware())
    app.mount_pages(str(pages_dir))
    return app


async def _csrf_context(client: TestClient) -> tuple[str, str]:
    response = await client.get("/")
    token = extract_csrf_token(response.text)
    cookie = extract_session_cookie(response, "chirp_session")
    assert token is not None
    assert cookie is not None
    return token, cookie


class TestProductionFormStack:
    async def test_mounted_form_contract_is_visible_with_csrf_fields(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        _write_product_form_pages(pages_dir)
        app = _product_form_app(pages_dir)

        result = check_hypermedia_surface(app)
        form_issues = [issue for issue in result.issues if issue.category == "form"]

        assert form_issues == []
        assert result.forms_validated == 1

    async def test_csrf_form_from_repeated_fields_and_submit_intent(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        _write_product_form_pages(pages_dir)
        app = _product_form_app(pages_dir)

        async with TestClient(app) as client:
            token, cookie = await _csrf_context(client)
            body = urlencode(
                {
                    "_csrf_token": token,
                    "title": "Launch notes",
                    "tags": ["docs", "bug"],
                    "intent": "publish",
                },
                doseq=True,
            ).encode()
            response = await client.post(
                "/",
                body=body,
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

        assert response.status == 200
        assert response.text == "publish:Launch notes:docs,bug"

    async def test_non_htmx_binding_error_returns_form_fragment(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        _write_product_form_pages(pages_dir)
        app = _product_form_app(pages_dir)

        async with TestClient(app) as client:
            token, cookie = await _csrf_context(client)
            body = urlencode(
                {"_csrf_token": token, "tags": ["docs"], "intent": "save"},
                doseq=True,
            ).encode()
            response = await client.post(
                "/",
                body=body,
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

        assert response.status == 422
        assert "<html>" not in response.text
        assert "title: title is required." in response.text

    async def test_htmx_business_validation_retargets_form(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        _write_product_form_pages(pages_dir)
        app = _product_form_app(pages_dir)

        async with TestClient(app) as client:
            token, cookie = await _csrf_context(client)
            body = urlencode(
                {
                    "_csrf_token": token,
                    "title": "Launch notes",
                    "tags": ["docs"],
                    "intent": "archive",
                },
                doseq=True,
            ).encode()
            response = await client.post(
                "/",
                body=body,
                headers={
                    "Cookie": f"chirp_session={cookie}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "HX-Request": "true",
                },
            )

        assert response.status == 422
        assert response.header("hx-retarget") == "#composer"
        assert "intent: Unknown action" in response.text
