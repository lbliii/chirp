"""Issue #546: htmx 4 request metadata must preserve typed negotiation."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Page
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(546)


def _app(tmp_path: Path) -> App:
    (tmp_path / "page.html").write_text(
        """<!DOCTYPE html>
<html><body>
{% block page_root %}<main id="page-root">
  <h1>Wide page block</h1>
  {% block results %}<section id="results">Narrow results</section>{% endblock %}
</main>{% endblock %}
</body></html>
"""
    )
    app = App(AppConfig(template_dir=tmp_path))

    @app.route("/")
    def index():
        return Page("page.html", "results", page_block_name="page_root")

    return app


async def test_tagged_partial_target_renders_only_named_fragment(tmp_path: Path) -> None:
    async with TestClient(_app(tmp_path)) as client:
        response = await client.fragment(
            "/",
            target="section#results",
            source="button#search",
            request_type="partial",
        )

    assert response.status == 200
    assert '<section id="results">Narrow results</section>' in response.text
    assert "Wide page block" not in response.text
    assert "<!DOCTYPE" not in response.text
    assert response.header("x-chirp-render-intent") == "fragment"
    assert response.header("vary") == "HX-Request, HX-Request-Type"


async def test_full_body_request_renders_page_block_not_narrow_block(tmp_path: Path) -> None:
    async with TestClient(_app(tmp_path)) as client:
        response = await client.fragment(
            "/",
            target="body",
            source="a#home",
            request_type="full",
        )

    assert response.status == 200
    assert "Wide page block" in response.text
    assert "Narrow results" in response.text
    assert response.header("x-chirp-render-intent") == "fragment"


async def test_full_header_cannot_widen_malformed_narrow_target(tmp_path: Path) -> None:
    async with TestClient(_app(tmp_path)) as client:
        response = await client.fragment(
            "/",
            target="#results child",
            source="button#search",
            request_type="full",
        )

    assert response.status == 200
    assert '<section id="results">Narrow results</section>' in response.text
    assert "Wide page block" not in response.text
    assert "<!DOCTYPE" not in response.text


async def test_request_type_without_hx_request_does_not_claim_htmx(tmp_path: Path) -> None:
    async with TestClient(_app(tmp_path)) as client:
        response = await client.get(
            "/",
            headers={"HX-Request-Type": "partial", "Accept": "text/html"},
        )

    assert response.status == 200
    assert "<!DOCTYPE html>" in response.text
    assert response.header("x-chirp-render-intent") == "full_page"
