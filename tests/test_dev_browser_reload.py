"""Tests for debug browser reload wiring."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from chirp import App, AppConfig, Page, Template
from chirp.server.dev_browser_reload import (
    DEV_BROWSER_RELOAD_SNIPPET,
    DEV_RELOAD_SSE_PATH,
    _build_template_reload_planner,
    _template_reload_plan_event,
    _template_reload_plan_events,
)
from chirp.templating.dev_template_reload import (
    TemplateReloadPlan,
    TemplateReloadSurface,
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


@pytest.mark.issue(681)
async def test_reload_planner_is_absent_when_debug_is_disabled(tmp_path: Path) -> None:
    _write_page_template(tmp_path)
    app = App(
        AppConfig(
            debug=False,
            dev_browser_reload=True,
            template_dir=tmp_path,
        )
    )

    @app.route("/")
    def index():
        return Template("page.html", msg="hello")

    async with TestClient(app) as client:
        page = await client.get("/")
        reload_route = await client.get(DEV_RELOAD_SSE_PATH)

    assert reload_route.status == 404
    assert "chirp:reload-plan" not in page.text


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
var reloads = 0;
global.location = {{ reload: function() {{ reloads++; }} }};
global.setTimeout = function(fn, delay) {{ return delay; }};
var calls = [];
var listeners = {{}};
var dispatched = [];
global.CustomEvent = function(name, options) {{ this.type = name; this.detail = options.detail; }};
global.dispatchEvent = function(evt) {{ dispatched.push(evt); }};
function FakeEventSource(url) {{
  calls.push(url);
  this.addEventListener = function(name, fn) {{ listeners[name] = fn; }};
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
listeners.planner({{ data: "not-json" }});
if (dispatched.length !== 0 || reloads !== 0) {{
  throw new Error("invalid planner state was not ignored");
}}
listeners.planner({{ data: '{{"schema_version":1,"revision":7,"outcome":"reload","reason":"target_ambiguous"}}' }});
if (dispatched.length !== 1 || dispatched[0].type !== "chirp:reload-plan") {{
  throw new Error("planner event was not projected to DevTools");
}}
if (dispatched[0].detail.revision !== 7 || reloads !== 0) {{
  throw new Error("planner projection mutated reload behavior");
}}
listeners.reload();
if (reloads !== 1) throw new Error("full reload behavior changed");
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


@pytest.mark.issue(681)
def test_template_reload_plan_event_is_versioned_and_redacted() -> None:
    plan = TemplateReloadPlan(
        revision=9,
        outcome="reload",
        reason="target_ambiguous",
        template_name="markets/page.html",
        changed_blocks=("movers",),
        target_id="main",
    )

    event = _template_reload_plan_event(plan)
    payload = json.loads(event.data)

    assert event.event == "planner"
    assert payload == {
        "added_blocks": [],
        "changed_blocks": ["movers"],
        "error_line": None,
        "error_type": None,
        "outcome": "reload",
        "reason": "target_ambiguous",
        "removed_blocks": [],
        "requires_response_validation": False,
        "revision": 9,
        "schema_version": 1,
        "target_id": "main",
        "template_name": "markets/page.html",
    }
    serialized = event.data
    assert "source_filename" not in serialized
    assert "context" not in serialized


@pytest.mark.issue(681)
def test_compile_diagnostic_event_preserves_only_error_type_and_line() -> None:
    event = _template_reload_plan_event(
        TemplateReloadPlan(
            revision=10,
            outcome="diagnose",
            reason="template_compile_error",
            template_name="markets/page.html",
            error_type="ParseError",
            error_line=17,
        )
    )

    payload = json.loads(event.data)

    assert payload["outcome"] == "diagnose"
    assert payload["error_type"] == "ParseError"
    assert payload["error_line"] == 17
    assert set(payload) == {
        "added_blocks",
        "changed_blocks",
        "error_line",
        "error_type",
        "outcome",
        "reason",
        "removed_blocks",
        "requires_response_validation",
        "revision",
        "schema_version",
        "target_id",
        "template_name",
    }


@pytest.mark.issue(681)
def test_frozen_app_builds_planner_but_empty_browser_facts_force_reload(tmp_path) -> None:
    template = tmp_path / "page.html"
    template.write_text(
        "{% block first %}one{% end %}{% block second %}stable{% end %}",
        encoding="utf-8",
    )
    app = App(AppConfig(debug=True, dev_browser_reload=True, template_dir=tmp_path))
    app.register_fragment_target("main", fragment_block="first")

    @app.route("/", template="page.html")
    def index():
        return Template("page.html")

    app.freeze()
    planner = _build_template_reload_planner(
        app._runtime_state,
        app._runtime_state.fragment_target_registry,
    )
    assert planner is not None
    template.write_text(
        "{% block first %}changed{% end %}{% block second %}stable{% end %}",
        encoding="utf-8",
    )

    [event] = _template_reload_plan_events([template], planner)
    payload = json.loads(event.data)

    assert payload["revision"] == 1
    assert payload["outcome"] == "reload"
    assert payload["reason"] == "not_current_route_template"
    assert payload["changed_blocks"] == ["first"]


@pytest.mark.issue(681)
def test_concurrent_reload_connections_share_one_plan_per_file_revision(tmp_path) -> None:
    template = tmp_path / "page.html"
    template.write_text(
        "{% block first %}one{% end %}{% block second %}stable{% end %}",
        encoding="utf-8",
    )
    app = App(AppConfig(debug=True, dev_browser_reload=True, template_dir=tmp_path))
    app.register_fragment_target("main", fragment_block="first")

    @app.route("/", template="page.html")
    def index():
        return Template("page.html")

    app.freeze()
    planner = _build_template_reload_planner(
        app._runtime_state,
        app._runtime_state.fragment_target_registry,
    )
    assert planner is not None
    template.write_text(
        "{% block first %}changed{% end %}{% block second %}stable{% end %}",
        encoding="utf-8",
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        events = list(
            executor.map(
                lambda _index: _template_reload_plan_events([template], planner)[0],
                range(24),
            )
        )

    payloads = [json.loads(event.data) for event in events]
    assert {payload["revision"] for payload in payloads} == {1}
    assert {payload["reason"] for payload in payloads} == {"not_current_route_template"}


@pytest.mark.issue(681)
def test_changed_html_files_emit_monotonic_plans_with_fail_closed_surface(tmp_path) -> None:
    class RecordingPlanner:
        def __init__(self) -> None:
            self.surfaces: list[TemplateReloadSurface] = []

        def plan_edit(self, path: Path, surface: TemplateReloadSurface) -> TemplateReloadPlan:
            self.surfaces.append(surface)
            return TemplateReloadPlan(
                revision=len(self.surfaces),
                outcome="reload",
                reason="not_current_route_template",
                template_name=path.name,
            )

    planner = RecordingPlanner()
    events = _template_reload_plan_events(
        [tmp_path / "z.html", tmp_path / "style.css", tmp_path / "a.html"],
        planner,
    )

    payloads = [json.loads(event.data) for event in events]
    assert [payload["revision"] for payload in payloads] == [1, 2]
    assert [payload["template_name"] for payload in payloads] == ["a.html", "z.html"]
    assert all(event.event == "planner" for event in events)
    assert planner.surfaces == [TemplateReloadSurface(), TemplateReloadSurface()]
