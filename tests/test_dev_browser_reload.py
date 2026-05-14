"""Tests for debug browser reload wiring."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from chirp import App, AppConfig, Page, Template
from chirp.server.dev_browser_reload import (
    DEV_BROWSER_RELOAD_SNIPPET,
    DEV_RELOAD_SSE_PATH,
)
from chirp.testing import TestClient


def _write_page_template(template_dir: Path) -> None:
    (template_dir / "page.html").write_text(
        "{% block page_root %}"
        '<html><body><main id="main">{% block content %}{{ msg }}{% end %}</main></body></html>'
        "{% end %}"
    )


def _dev_reload_count(html: str) -> int:
    return html.count(DEV_RELOAD_SSE_PATH)


async def test_dev_browser_reload_injects_once_on_full_page(tmp_path: Path) -> None:
    """A full browser document gets one dev reload bootstrap."""
    _write_page_template(tmp_path)
    app = App(AppConfig(debug=True, dev_browser_reload=True, template_dir=tmp_path))

    @app.route("/")
    def index():
        return Template("page.html", msg="hello")

    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.status == 200
    assert _dev_reload_count(response.text) == 1
    assert response.text.count("new EventSource") == 1


async def test_dev_browser_reload_skips_htmx_full_page_response(tmp_path: Path) -> None:
    """Browser reload is never injected into htmx responses, even full-page ones."""
    _write_page_template(tmp_path)
    app = App(AppConfig(debug=True, dev_browser_reload=True, template_dir=tmp_path))

    @app.route("/")
    def index():
        return Template("page.html", msg="hello")

    async with TestClient(app) as client:
        response = await client.get("/", headers={"HX-Request": "true"})

    assert response.status == 200
    assert _dev_reload_count(response.text) == 0


async def test_dev_browser_reload_skips_boosted_page_fragment(tmp_path: Path) -> None:
    """Boosted Page responses are fragments and must not boot browser reload."""
    _write_page_template(tmp_path)
    app = App(AppConfig(debug=True, dev_browser_reload=True, template_dir=tmp_path))

    @app.route("/")
    def index():
        return Page("page.html", "content", page_block_name="page_root", msg="hello")

    async with TestClient(app) as client:
        response = await client.fragment("/", target="main", headers={"HX-Boosted": "true"})

    assert response.status == 200
    assert response.header("x-chirp-render-intent") == "fragment"
    assert _dev_reload_count(response.text) == 0


async def test_reload_include_empty_disables_browser_reload(tmp_path: Path) -> None:
    """reload_include=() opts out of both reload injection and reload route registration."""
    _write_page_template(tmp_path)
    app = App(
        AppConfig(
            debug=True,
            dev_browser_reload=True,
            reload_include=(),
            template_dir=tmp_path,
        )
    )

    @app.route("/")
    def index():
        return Template("page.html", msg="hello")

    async with TestClient(app) as client:
        page = await client.get("/")
        reload_route = await client.get(DEV_RELOAD_SSE_PATH)

    assert _dev_reload_count(page.text) == 0
    assert reload_route.status == 404


def test_dev_browser_reload_snippet_is_idempotent() -> None:
    """Executing the browser reload snippet twice opens one EventSource."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found - install Node.js to validate reload snippet behavior")

    match = re.fullmatch(r"<script>\n(?P<script>.*)\n</script>", DEV_BROWSER_RELOAD_SNIPPET, re.S)
    assert match is not None
    snippet = match.group("script")
    js = f"""
global.window = global;
global.location = {{ reload: function() {{}} }};
global.setTimeout = function(fn, delay) {{ return delay; }};
var calls = [];
function FakeEventSource(url) {{
  calls.push(url);
  this.addEventListener = function() {{}};
  this.close = function() {{ calls.push("close:" + url); }};
}}
global.EventSource = FakeEventSource;
{snippet}
{snippet}
if (calls.length !== 1) {{
  throw new Error("expected one EventSource, got " + calls.length + ": " + calls.join(","));
}}
if (calls[0] !== "{DEV_RELOAD_SSE_PATH}") {{
  throw new Error("unexpected EventSource URL " + calls[0]);
}}
if (!global.__chirpDevReloadBooted || !global.__chirpDevReloadSource) {{
  throw new Error("reload globals were not set");
}}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        path = f.name

    try:
        result = subprocess.run(
            [node, path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.unlink(path)
