"""Tests for chirp.contracts — typed hypermedia contract validation."""

from dataclasses import dataclass
from types import SimpleNamespace

from chirp.app import App
from chirp.config import AppConfig
from chirp.contracts import (
    CheckResult,
    ContractIssue,
    FormContract,
    FragmentContract,
    RouteContract,
    Severity,
    SSEContract,
    _attr_to_method,
    _check_accessibility,
    _check_island_mounts,
    _check_sse_connect_scope,
    _check_sse_self_swap,
    _check_swap_safety,
    _collect_broad_targets,
    _extract_form_field_names,
    _extract_island_mounts,
    _extract_targets_from_source,
    _extract_template_references,
    _path_matches_route,
    check_hypermedia_surface,
    contract,
)


class TestAttrToMethod:
    """Map htmx attribute names to HTTP methods."""

    def test_hx_get(self):
        assert _attr_to_method("hx-get") == "GET"

    def test_hx_post(self):
        assert _attr_to_method("hx-post") == "POST"

    def test_hx_put(self):
        assert _attr_to_method("hx-put") == "PUT"

    def test_hx_delete(self):
        assert _attr_to_method("hx-delete") == "DELETE"

    def test_hx_patch(self):
        assert _attr_to_method("hx-patch") == "PATCH"

    def test_form_action(self):
        assert _attr_to_method("action") == "POST"


class TestExtractTargets:
    """Extract htmx targets from template HTML source."""

    def test_hx_get(self):
        html = '<div hx-get="/api/search"></div>'
        targets = _extract_targets_from_source(html)
        assert len(targets) == 1
        assert targets[0] == ("hx-get", "/api/search")

    def test_hx_post(self):
        html = '<button hx-post="/submit"></button>'
        targets = _extract_targets_from_source(html)
        assert targets[0] == ("hx-post", "/submit")

    def test_form_action(self):
        html = '<form action="/login" method="post"></form>'
        targets = _extract_targets_from_source(html)
        assert targets[0] == ("action", "/login")

    def test_multiple_targets(self):
        html = '''
        <div hx-get="/api/items"></div>
        <button hx-post="/api/items" hx-target="#list"></button>
        <form action="/search"></form>
        '''
        targets = _extract_targets_from_source(html)
        assert len(targets) == 3

    def test_ignores_template_expressions(self):
        html = '<div hx-get="{{ url_for(\'search\') }}"></div>'
        targets = _extract_targets_from_source(html)
        assert len(targets) == 0

    def test_ignores_anchors(self):
        html = '<div hx-get="#section"></div>'
        targets = _extract_targets_from_source(html)
        assert len(targets) == 0

    def test_single_quotes(self):
        html = "<div hx-get='/api/data'></div>"
        targets = _extract_targets_from_source(html)
        assert targets[0] == ("hx-get", "/api/data")

    def test_empty_source(self):
        assert _extract_targets_from_source("") == []


class TestIslandMountExtraction:
    def test_extract_mount_with_props_and_src(self):
        html = (
            '<div data-island="chart" id="sales-chart" '
            'data-island-version="1" '
            'data-island-src="/static/chart.js" data-island-props="{&quot;series&quot;:[1,2]}"></div>'
        )
        mounts = _extract_island_mounts(html)
        assert len(mounts) == 1
        assert mounts[0]["name"] == "chart"
        assert mounts[0]["mount_id"] == "sales-chart"
        assert mounts[0]["version"] == "1"
        assert mounts[0]["src"] == "/static/chart.js"
        assert mounts[0]["primitive"] is None

    def test_extract_mount_with_primitive(self):
        html = '<div data-island="grid_state" data-island-primitive="grid_state"></div>'
        mounts = _extract_island_mounts(html)
        assert len(mounts) == 1
        assert mounts[0]["primitive"] == "grid_state"

    def test_empty_when_no_mounts(self):
        assert _extract_island_mounts("<div>No island</div>") == []


class TestIslandMountValidation:
    def test_malformed_props_json_errors(self):
        sources = {"index.html": '<div data-island="chart" data-island-props="{oops"></div>'}
        issues = _check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "islands"

    def test_missing_id_warns_in_strict_mode(self):
        sources = {
            "index.html": (
                '<div data-island="editor" data-island-version="1" '
                'data-island-props="{&quot;a&quot;:1}"></div>'
            )
        }
        issues = _check_island_mounts(sources, strict=True)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "islands"

    def test_valid_mount_has_no_issues(self):
        sources = {
            "index.html": (
                '<div data-island="editor" id="editor-root" '
                'data-island-version="1" '
                'data-island-props="{&quot;a&quot;:1}"></div>'
            )
        }
        issues = _check_island_mounts(sources, strict=True)
        assert issues == []

    def test_missing_version_warns_in_strict_mode(self):
        sources = {
            "index.html": (
                '<div data-island="editor" id="editor-root" '
                'data-island-props="{&quot;a&quot;:1}"></div>'
            )
        }
        issues = _check_island_mounts(sources, strict=True)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert "data-island-version" in issues[0].message

    def test_invalid_version_errors(self):
        sources = {
            "index.html": '<div data-island="editor" data-island-version="1 beta"></div>'
        }
        issues = _check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "invalid data-island-version" in issues[0].message

    def test_unsafe_src_errors(self):
        sources = {
            "index.html": '<div data-island="editor" data-island-src="javascript:alert(1)"></div>'
        }
        issues = _check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "unsafe data-island-src" in issues[0].message

    def test_primitive_required_props_error(self):
        sources = {
            "index.html": (
                '<div data-island="grid_state" data-island-primitive="grid_state" '
                'data-island-props="{&quot;stateKey&quot;:&quot;grid&quot;}"></div>'
            )
        }
        issues = _check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "required props: columns" in issues[0].message

    def test_primitive_object_props_required(self):
        sources = {
            "index.html": (
                '<div data-island="wizard_state" data-island-primitive="wizard_state" '
                'data-island-props="[1,2,3]"></div>'
            )
        }
        issues = _check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "expects object-like props" in issues[0].message

    def test_primitive_missing_props_errors(self):
        sources = {
            "index.html": '<div data-island="upload_state" data-island-primitive="upload_state"></div>'
        }
        issues = _check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "must define data-island-props" in issues[0].message


class TestPathMatchesRoute:
    """Path matching between htmx URLs and route patterns."""

    def test_exact_match(self):
        assert _path_matches_route("/api/items", "/api/items")

    def test_no_match(self):
        assert not _path_matches_route("/api/items", "/api/users")

    def test_param_match(self):
        assert _path_matches_route("/api/items/42", "/api/items/{id}")

    def test_typed_param_match(self):
        assert _path_matches_route("/api/items/42", "/api/items/{id:int}")

    def test_multiple_params(self):
        assert _path_matches_route("/users/1/posts/5", "/users/{uid}/posts/{pid}")

    def test_different_length(self):
        assert not _path_matches_route("/api/items/42/extra", "/api/items/{id}")

    def test_root_path(self):
        assert _path_matches_route("/", "/")

    def test_query_string_stripped(self):
        """URLs with query params match route path (htmx hx-get with ?page=1 etc)."""
        assert _path_matches_route("/data/table?page=1&sort=name", "/data/table")
        assert _path_matches_route("/layout/dir?dir=ltr", "/layout/dir")
        assert _path_matches_route("/layout/dir?dir=rtl", "/layout/dir")
        assert _path_matches_route("/api/items?filter=active", "/api/items")

    def test_query_string_with_param_route(self):
        """Query string stripped before matching param routes."""
        assert _path_matches_route("/api/items/42?expand=details", "/api/items/{id}")


class TestContractDecorator:
    """The @contract decorator attaches metadata to handlers."""

    def test_attaches_contract(self):
        @contract(returns=FragmentContract("search.html", "results"))
        async def handler():
            pass

        assert hasattr(handler, "_chirp_contract")
        rc = handler._chirp_contract
        assert isinstance(rc, RouteContract)
        assert isinstance(rc.returns, FragmentContract)
        assert rc.returns.template == "search.html"
        assert rc.returns.block == "results"

    def test_sse_contract(self):
        @contract(returns=SSEContract(event_types=frozenset({"update", "delete"})))
        async def handler():
            pass

        rc = handler._chirp_contract
        assert isinstance(rc.returns, SSEContract)
        assert "update" in rc.returns.event_types

    def test_description(self):
        @contract(description="Search endpoint")
        async def handler():
            pass

        assert handler._chirp_contract.description == "Search endpoint"


class TestCheckResult:
    """CheckResult aggregation and reporting."""

    def test_ok_when_no_errors(self):
        result = CheckResult()
        assert result.ok

    def test_not_ok_with_errors(self):
        result = CheckResult(issues=[
            ContractIssue(severity=Severity.ERROR, category="test", message="fail"),
        ])
        assert not result.ok

    def test_ok_with_warnings_only(self):
        result = CheckResult(issues=[
            ContractIssue(severity=Severity.WARNING, category="test", message="warn"),
        ])
        assert result.ok

    def test_summary_no_issues(self):
        result = CheckResult(routes_checked=5, templates_scanned=3, targets_found=10)
        summary = result.summary()
        assert "5 routes" in summary
        assert "3 templates" in summary
        assert "No issues found" in summary

    def test_summary_with_errors(self):
        result = CheckResult(
            routes_checked=1,
            templates_scanned=1,
            targets_found=1,
            issues=[
                ContractIssue(
                    severity=Severity.ERROR,
                    category="target",
                    message="'/missing' has no matching route.",
                    template="index.html",
                ),
            ],
        )
        summary = result.summary()
        assert "1 error" in summary
        assert "/missing" in summary


class TestCheckAccessibility:
    """_check_accessibility warns on hx-* attrs on non-interactive elements."""

    def test_div_with_hx_get_warns(self):
        html = '<div hx-get="/items">load</div>'
        issues = _check_accessibility(html, "test.html")
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "accessibility"
        assert "<div>" in issues[0].message
        assert issues[0].template == "test.html"

    def test_span_with_hx_post_warns(self):
        html = '<span class="btn" hx-post="/submit">go</span>'
        issues = _check_accessibility(html, "form.html")
        assert len(issues) == 1
        assert "<span>" in issues[0].message

    def test_button_is_interactive_no_warning(self):
        html = '<button hx-post="/submit">go</button>'
        issues = _check_accessibility(html, "form.html")
        assert len(issues) == 0

    def test_a_tag_is_interactive_no_warning(self):
        html = '<a hx-get="/page" hx-push-url="true">link</a>'
        issues = _check_accessibility(html, "nav.html")
        assert len(issues) == 0

    def test_input_is_interactive_no_warning(self):
        html = '<input hx-get="/search" hx-trigger="keyup">'
        issues = _check_accessibility(html, "search.html")
        assert len(issues) == 0

    def test_form_is_interactive_no_warning(self):
        html = '<form hx-post="/submit">...</form>'
        issues = _check_accessibility(html, "form.html")
        assert len(issues) == 0

    def test_div_with_role_no_warning(self):
        html = '<div role="button" hx-get="/items">load</div>'
        issues = _check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_div_with_tabindex_no_warning(self):
        html = '<div tabindex="0" hx-get="/items">load</div>'
        issues = _check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_div_with_role_and_tabindex_no_warning(self):
        html = '<div role="button" tabindex="0" hx-post="/action">do</div>'
        issues = _check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_multiple_elements_mixed(self):
        html = """
        <button hx-post="/ok">good</button>
        <div hx-get="/bad">bad</div>
        <a hx-get="/fine">fine</a>
        <span hx-delete="/also-bad">bad</span>
        <li role="button" hx-get="/ok-with-role">ok</li>
        """
        issues = _check_accessibility(html, "mixed.html")
        # Only <div> and <span> should warn (li has role)
        assert len(issues) == 2
        messages = [i.message for i in issues]
        assert any("<div>" in m for m in messages)
        assert any("<span>" in m for m in messages)

    def test_no_hx_url_attrs_no_warnings(self):
        html = '<div class="container"><span>text</span></div>'
        issues = _check_accessibility(html, "test.html")
        assert len(issues) == 0

    def test_section_with_hx_get_warns(self):
        html = '<section hx-get="/content">loading...</section>'
        issues = _check_accessibility(html, "test.html")
        assert len(issues) == 1
        assert "<section>" in issues[0].message

    def test_tr_with_hx_get_warns(self):
        html = '<tr hx-get="/row/1">...</tr>'
        issues = _check_accessibility(html, "table.html")
        assert len(issues) == 1
        assert "<tr>" in issues[0].message


class TestSwapSafetyWarnings:
    """Warnings for broad inherited hx-target plus mutating requests."""

    def test_warns_for_mutation_without_local_target(self):
        template_sources = {
            "_layout.html": (
                '<body hx-boost="true" hx-target="#app-content">'
                "<main>{% block content %}{% endblock %}</main>"
                "</body>"
            ),
            "docs.html": '<form hx-post="/docs/new"><button>Save</button></form>',
        }
        issues = _check_swap_safety(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "swap_safety"
        assert "Action()" in issues[0].message

    def test_no_warning_when_mutation_has_local_target(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "docs.html": (
                '<form hx-post="/docs/new" hx-target="#editor">'
                "<button>Save</button>"
                "</form>"
            ),
        }
        issues = _check_swap_safety(template_sources)
        assert issues == []

    def test_no_warning_when_swap_none(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "docs.html": '<form hx-post="/docs/new" hx-swap="none"></form>',
        }
        issues = _check_swap_safety(template_sources)
        assert issues == []

    def test_warns_for_sse_swap_without_local_target(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/events">'
                '<span sse-swap="fragment" hx-swap="beforeend"></span>'
                "</div>"
            ),
        }
        issues = _check_swap_safety(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "swap_safety"
        assert "SSE swap element has no explicit hx-target" in issues[0].message

    def test_no_warning_for_sse_swap_with_local_target(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/events">'
                '<span sse-swap="fragment" hx-swap="beforeend" hx-target="this"></span>'
                "</div>"
            ),
        }
        issues = _check_swap_safety(template_sources)
        assert issues == []

    def test_no_warning_for_sse_swap_when_connect_has_disinherit(self):
        """sse-connect with hx-disinherit skips WARNING; INFO suggests hx-target."""
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#main"></body>',
            "ask.html": (
                '<article hx-ext="sse" sse-connect="{{ stream_url }}" '
                'hx-disinherit="hx-target hx-swap">'
                '<div class="answer" sse-swap="answer">...</div>'
                "</article>"
            ),
        }
        issues = _check_swap_safety(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.INFO
        assert "hx-target" in issues[0].message

    def test_no_info_when_sse_swap_has_hx_target_this(self):
        """sse-swap with hx-target='this' gets no INFO suggestion."""
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#main"></body>',
            "ask.html": (
                '<article hx-ext="sse" sse-connect="{{ stream_url }}" '
                'hx-disinherit="hx-target hx-swap">'
                '<div class="answer" sse-swap="answer" hx-target="this">...</div>'
                "</article>"
            ),
        }
        issues = _check_swap_safety(template_sources)
        assert issues == []


class TestCheckHypermediaSurface:
    """Integration test for the full hypermedia check."""

    def test_app_with_no_routes(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))
        result = check_hypermedia_surface(app)
        assert result.routes_checked == 0

    def test_detects_flask_style_route_path(self, tmp_path, monkeypatch):
        """Contract check reports route path using <param> instead of {param}."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items")
        async def list_items():
            return "ok"

        # Simulate a route with Flask-style path (normally caught at freeze)
        def fake_has_flask_syntax(path: str) -> bool:
            return path == "/api/items"

        monkeypatch.setattr(
            "chirp.contracts._route_path_has_flask_syntax", fake_has_flask_syntax
        )
        result = check_hypermedia_surface(app)
        assert not result.ok
        routing_errors = [i for i in result.issues if i.category == "routing"]
        assert len(routing_errors) == 1
        assert "<param>" in routing_errors[0].message
        assert "{param}" in routing_errors[0].message

    def test_app_with_matching_routes(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items")
        async def list_items():
            return "ok"

        @app.route("/api/items", methods=["POST"])
        async def create_item():
            return "ok"

        result = check_hypermedia_surface(app)
        # Same path, different methods = 1 unique path
        assert result.routes_checked == 1
        # No templates to scan, so no target issues
        assert result.ok

    def test_detects_unmatched_hx_target(self, tmp_path):
        """Template references a route that doesn't exist."""
        # Write a template with an htmx target
        (tmp_path / "index.html").write_text(
            '<div hx-get="/api/missing">load</div>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        assert not result.ok
        assert any("no matching route" in i.message for i in result.errors)

    def test_detects_method_mismatch(self, tmp_path):
        """Template uses hx-post but route only allows GET."""
        (tmp_path / "index.html").write_text(
            '<button hx-post="/api/items">submit</button>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items")  # GET only
        async def list_items():
            return "ok"

        result = check_hypermedia_surface(app)
        assert not result.ok
        assert any("POST" in i.message and "GET" in i.message for i in result.errors)

    def test_valid_hx_targets(self, tmp_path):
        """All htmx targets match registered routes."""
        (tmp_path / "index.html").write_text(
            '<div hx-get="/api/items">load</div>'
            '<button hx-post="/api/items">add</button>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items")
        async def list_items():
            return "ok"

        @app.route("/api/items", methods=["POST"])
        async def create_item():
            return "ok"

        result = check_hypermedia_surface(app)
        assert result.ok
        assert result.targets_found == 2

    def test_hx_get_with_query_params_matches_route(self, tmp_path):
        """hx-get URLs with query params match routes (component-showcase-like setup).

        Regression: chirp check must not report false 'has no matching route'
        for URLs like /data/table?page=1&sort=name when /data/table exists.
        _path_matches_route strips query strings before matching.
        """
        (tmp_path / "showcase").mkdir()
        (tmp_path / "showcase" / "data.html").write_text(
            '<div hx-get="/data/table?page=1&sort=name" hx-trigger="load">Loading</div>'
        )
        (tmp_path / "showcase" / "layout.html").write_text(
            '<div hx-get="/layout/dir?dir=ltr">Toggle</div>'
        )
        app = App(
            AppConfig(
                template_dir=str(tmp_path),
                component_dirs=(str(tmp_path / "components"),),
            )
        )
        (tmp_path / "components").mkdir()
        (tmp_path / "components" / "_partial.html").write_text("<span></span>")

        @app.route("/data/table", methods=["GET"])
        async def data_table():
            return "ok"

        @app.route("/layout/dir", methods=["GET"])
        async def layout_dir():
            return "ok"

        result = check_hypermedia_surface(app)
        route_errors = [
            i for i in result.errors if "no matching route" in i.message
        ]
        assert not route_errors, (
            f"Expected no 'has no matching route' errors for URLs with query params, "
            f"got: {[e.message for e in route_errors]}"
        )
        assert result.targets_found >= 2

    def test_accessibility_warnings_in_surface_check(self, tmp_path):
        """Accessibility warnings surface through the full check."""
        (tmp_path / "index.html").write_text(
            '<div hx-get="/api/items">load</div>'
            '<button hx-post="/api/items">add</button>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items")
        async def list_items():
            return "ok"

        @app.route("/api/items", methods=["POST"])
        async def create_item():
            return "ok"

        result = check_hypermedia_surface(app)
        # Routes match, so no errors — but div triggers a11y warning
        assert result.ok
        a11y_warnings = [
            i for i in result.warnings if i.category == "accessibility"
        ]
        assert len(a11y_warnings) == 1
        assert "<div>" in a11y_warnings[0].message

    def test_no_accessibility_warnings_when_all_interactive(self, tmp_path):
        """No a11y warnings when all htmx attrs are on interactive elements."""
        (tmp_path / "index.html").write_text(
            '<a hx-get="/api/items">load</a>'
            '<button hx-post="/api/items">add</button>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items")
        async def list_items():
            return "ok"

        @app.route("/api/items", methods=["POST"])
        async def create_item():
            return "ok"

        result = check_hypermedia_surface(app)
        assert result.ok
        a11y_warnings = [
            i for i in result.warnings if i.category == "accessibility"
        ]
        assert len(a11y_warnings) == 0

    def test_swap_safety_warning_surfaces(self, tmp_path):
        """Broad hx-target + mutating request without local target warns."""
        (tmp_path / "_layout.html").write_text(
            '<body hx-boost="true" hx-target="#app-content">{% block content %}{% endblock %}</body>'
        )
        (tmp_path / "index.html").write_text(
            "{% block content %}"
            '<form hx-post="/docs/new"><button>Create</button></form>'
            "{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/docs/new", methods=["POST"])
        async def create_doc():
            return "ok"

        result = check_hypermedia_surface(app)
        swap_warnings = [
            issue for issue in result.warnings if issue.category == "swap_safety"
        ]
        assert len(swap_warnings) == 1
        assert "Action()" in swap_warnings[0].message


class TestExtractTemplateReferences:
    """Extract template references from Jinja source."""

    def test_extends(self):
        source = '{% extends "base.html" %}'
        assert _extract_template_references(source) == {"base.html"}

    def test_include(self):
        source = '{% include "partials/header.html" %}'
        assert _extract_template_references(source) == {"partials/header.html"}

    def test_from_import(self):
        source = '{% from "macros/forms.html" import text_field %}'
        assert _extract_template_references(source) == {"macros/forms.html"}

    def test_import_as(self):
        source = '{% import "macros/utils.html" as utils %}'
        assert _extract_template_references(source) == {"macros/utils.html"}

    def test_multiple_references(self):
        source = (
            '{% extends "base.html" %}\n'
            '{% include "nav.html" %}\n'
            '{% from "macros.html" import btn %}\n'
        )
        assert _extract_template_references(source) == {
            "base.html", "nav.html", "macros.html",
        }

    def test_single_quotes(self):
        source = "{% extends 'base.html' %}"
        assert _extract_template_references(source) == {"base.html"}

    def test_whitespace_trimming_tags(self):
        source = '{%- extends "base.html" -%}'
        assert _extract_template_references(source) == {"base.html"}

    def test_no_references(self):
        source = "<div>Hello</div>"
        assert _extract_template_references(source) == set()

    def test_ignores_dynamic_variable(self):
        source = "{% include template_name %}"
        assert _extract_template_references(source) == set()


def _user_dead(result: CheckResult) -> list[ContractIssue]:
    """Filter dead-template issues to only user templates (not built-in)."""
    def is_builtin(tmpl: str | None) -> bool:
        if not tmpl:
            return True
        return tmpl.startswith(("chirp/", "chirpui", "themes/"))

    return [
        i for i in result.issues
        if i.category == "dead" and not is_builtin(i.template)
    ]


class TestDeadTemplateDetection:
    """Integration tests for dead template detection in check_hypermedia_surface."""

    def test_unreferenced_template_reported(self, tmp_path):
        """An unused template should be reported as dead."""
        (tmp_path / "index.html").write_text(
            "{% block content %}<h1>Home</h1>{% endblock %}"
        )
        (tmp_path / "unused.html").write_text("<h1>Old page</h1>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 1
        assert "unused.html" in dead[0].message
        assert dead[0].severity == Severity.INFO

    def test_included_template_not_dead(self, tmp_path):
        """A template referenced via include should not be reported."""
        (tmp_path / "index.html").write_text(
            '{% block content %}{% include "nav.html" %}{% endblock %}'
        )
        (tmp_path / "nav.html").write_text("<nav>links</nav>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_extended_template_not_dead(self, tmp_path):
        """A template referenced via extends should not be reported."""
        (tmp_path / "base.html").write_text(
            "{% block content %}{% endblock %}"
        )
        (tmp_path / "page.html").write_text(
            '{% extends "base.html" %}{% block content %}hi{% endblock %}'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("page.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_partial_excluded_by_convention(self, tmp_path):
        """Templates with _ prefix are partials and should be excluded."""
        (tmp_path / "index.html").write_text(
            "{% block content %}<h1>Home</h1>{% endblock %}"
        )
        (tmp_path / "_partial.html").write_text("<p>partial</p>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_fragment_contract_template_not_dead(self, tmp_path):
        """A template referenced by a FragmentContract should not be dead."""
        (tmp_path / "search.html").write_text(
            "{% block results %}results{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/search")
        @contract(returns=FragmentContract("search.html", "results"))
        async def search():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0


class TestSSEFragmentValidation:
    """SSE fragment contract validation in check_hypermedia_surface."""

    def test_valid_sse_fragments(self, tmp_path):
        """SSE route with valid fragment declarations passes."""
        (tmp_path / "chat.html").write_text(
            "{% block message %}<p>msg</p>{% endblock %}"
            "{% block status %}<p>ok</p>{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(returns=SSEContract(
            event_types=frozenset({"message", "status"}),
            fragments=(
                FragmentContract("chat.html", "message"),
                FragmentContract("chat.html", "status"),
            ),
        ))
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 0
        assert result.sse_fragments_validated == 2

    def test_missing_template(self, tmp_path):
        """SSE route referencing a nonexistent template reports ERROR."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(returns=SSEContract(
            fragments=(FragmentContract("nonexistent.html", "body"),),
        ))
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 1
        assert "could not be loaded" in sse_errors[0].message

    def test_missing_block(self, tmp_path):
        """SSE route referencing a nonexistent block reports ERROR."""
        (tmp_path / "chat.html").write_text(
            "{% block message %}<p>msg</p>{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(returns=SSEContract(
            fragments=(FragmentContract("chat.html", "wrong_block"),),
        ))
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 1
        assert "doesn't exist" in sse_errors[0].message

    def test_empty_fragments_passes(self, tmp_path):
        """SSE route with no fragment declarations passes silently."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(returns=SSEContract(event_types=frozenset({"ping"})))
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 0
        assert result.sse_fragments_validated == 0


class TestExtractFormFieldNames:
    """Unit tests for _extract_form_field_names."""

    def test_input(self):
        html = '<input name="title" type="text">'
        assert _extract_form_field_names(html) == {"title"}

    def test_select(self):
        html = '<select name="status"><option>open</option></select>'
        assert _extract_form_field_names(html) == {"status"}

    def test_textarea(self):
        html = '<textarea name="body"></textarea>'
        assert _extract_form_field_names(html) == {"body"}

    def test_multiple_fields(self):
        html = (
            '<input name="title" type="text">'
            '<textarea name="body"></textarea>'
            '<select name="priority"><option>P1</option></select>'
        )
        assert _extract_form_field_names(html) == {"title", "body", "priority"}

    def test_excludes_csrf_token(self):
        html = '<input name="_csrf_token" type="hidden"><input name="title">'
        assert _extract_form_field_names(html) == {"title"}

    def test_skips_template_expressions(self):
        html = '<input name="{{ field_name }}">'
        assert _extract_form_field_names(html) == set()

    def test_empty_source(self):
        assert _extract_form_field_names("") == set()


class TestFormFieldValidation:
    """Integration tests for form field validation in check_hypermedia_surface."""

    def test_matching_fields_pass(self, tmp_path):
        """Template fields match dataclass fields — no issues."""

        @dataclass
        class TaskForm:
            title: str
            body: str

        (tmp_path / "tasks.html").write_text(
            '<form>'
            '<input name="title" type="text">'
            '<textarea name="body"></textarea>'
            '</form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "tasks.html"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_issues = [i for i in result.issues if i.category == "form"]
        assert len(form_issues) == 0
        assert result.forms_validated == 1

    def test_missing_field_reports_error(self, tmp_path):
        """Dataclass field missing from template = ERROR."""

        @dataclass
        class TaskForm:
            title: str
            body: str

        (tmp_path / "tasks.html").write_text(
            '<form><input name="title" type="text"></form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "tasks.html"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_errors = [i for i in result.errors if i.category == "form"]
        assert len(form_errors) == 1
        assert "body" in form_errors[0].message
        assert "TaskForm.body" in form_errors[0].message

    def test_extra_field_warns_with_suggestion(self, tmp_path):
        """Extra template field with typo = WARNING with 'did you mean?'."""

        @dataclass
        class TaskForm:
            title: str

        (tmp_path / "tasks.html").write_text(
            '<form>'
            '<input name="title" type="text">'
            '<input name="titl" type="text">'
            '</form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "tasks.html"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_warnings = [i for i in result.warnings if i.category == "form"]
        assert len(form_warnings) == 1
        assert "titl" in form_warnings[0].message
        assert "Did you mean 'title'?" in form_warnings[0].message

    def test_csrf_token_excluded(self, tmp_path):
        """Hidden CSRF token field should not trigger a warning."""

        @dataclass
        class LoginForm:
            username: str
            password: str

        (tmp_path / "login.html").write_text(
            '<form>'
            '<input name="_csrf_token" type="hidden">'
            '<input name="username" type="text">'
            '<input name="password" type="password">'
            '</form>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/login", methods=["POST"])
        @contract(form=FormContract(LoginForm, "login.html"))
        async def login():
            return "ok"

        result = check_hypermedia_surface(app)
        form_issues = [i for i in result.issues if i.category == "form"]
        assert len(form_issues) == 0

    def test_block_scoped_extraction(self, tmp_path):
        """FormContract with block= restricts field scanning to that block."""

        @dataclass
        class TaskForm:
            title: str

        (tmp_path / "page.html").write_text(
            '{% block header %}<input name="search">{% endblock %}'
            '{% block task_form %}'
            '<form><input name="title" type="text"></form>'
            '{% endblock %}'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/tasks", methods=["POST"])
        @contract(form=FormContract(TaskForm, "page.html", block="task_form"))
        async def add_task():
            return "ok"

        result = check_hypermedia_surface(app)
        form_issues = [i for i in result.issues if i.category == "form"]
        # "search" is in header block, not task_form — should not warn
        assert len(form_issues) == 0


class TestComponentCallValidation:
    """Component call validation via kida_env.validate_calls()."""

    def test_issues_surface_from_validate_calls(self, tmp_path):
        """When kida exposes validate_calls(), issues are forwarded."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        # Prepare mock issues from kida
        mock_issue = SimpleNamespace(
            is_error=True,
            message="card(titl='x') has no parameter 'titl'. Did you mean 'title'?",
            template="board.html",
        )

        app._ensure_frozen()
        kida_env = app._kida_env
        # Temporarily add validate_calls to the environment
        kida_env.validate_calls = lambda: [mock_issue]
        try:
            result = check_hypermedia_surface(app)
        finally:
            del kida_env.validate_calls

        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 1
        assert comp_issues[0].severity == Severity.ERROR
        assert "titl" in comp_issues[0].message
        assert comp_issues[0].template == "board.html"
        assert result.component_calls_validated == 1

    def test_warning_severity_forwarded(self, tmp_path):
        """Non-error issues from validate_calls come through as WARNING."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        mock_issue = SimpleNamespace(
            is_error=False,
            message="card() missing optional parameter 'footer'.",
            template="board.html",
        )

        app._ensure_frozen()
        kida_env = app._kida_env
        kida_env.validate_calls = lambda: [mock_issue]
        try:
            result = check_hypermedia_surface(app)
        finally:
            del kida_env.validate_calls

        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 1
        assert comp_issues[0].severity == Severity.WARNING

    def test_graceful_noop_without_validate_calls(self, tmp_path):
        """When kida doesn't have validate_calls, no component issues."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        comp_issues = [i for i in result.issues if i.category == "component"]
        assert len(comp_issues) == 0
        assert result.component_calls_validated == 0


class TestPageContextGaps:
    """Tests for Page context gap detection (check 9).

    When a route uses FragmentContract, the target block may only use
    a subset of the full template's variables.  Full-page Page renders
    evaluate the entire template, so missing variables cause runtime
    errors.  The checker should warn about this gap.
    """

    def test_gap_detected_when_extra_vars_in_other_blocks(self, tmp_path):
        """Template with two blocks where one uses vars the other doesn't."""
        (tmp_path / "page.html").write_text(
            "{% block detail %}{{ detail.name }}{% endblock %}"
            "{% block grid %}{{ pokemon }}{{ current_type }}{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/detail")
        @contract(returns=FragmentContract("page.html", "detail"))
        async def detail():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 1
        assert ctx_issues[0].severity == Severity.WARNING
        assert "current_type" in ctx_issues[0].message or "pokemon" in ctx_issues[0].message
        assert result.page_context_warnings == 1

    def test_no_gap_when_block_uses_all_vars(self, tmp_path):
        """When the block uses the same vars as the full template, no warning."""
        (tmp_path / "page.html").write_text(
            "{% block content %}{{ title }}{{ body }}{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("page.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 0
        assert result.page_context_warnings == 0

    def test_no_gap_for_single_block_templates(self, tmp_path):
        """Template with just one block — no gap possible."""
        (tmp_path / "simple.html").write_text(
            "{% block main %}<h1>{{ title }}</h1>{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("simple.html", "main"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 0

    def test_route_without_fragment_contract_skipped(self, tmp_path):
        """Routes without FragmentContract should not trigger this check."""
        (tmp_path / "page.html").write_text(
            "{% block a %}{{ x }}{% endblock %}"
            "{% block b %}{{ y }}{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        ctx_issues = [i for i in result.issues if i.category == "page_context"]
        assert len(ctx_issues) == 0


# ---------------------------------------------------------------------------
# SSE self-swap check — sse-swap on same element as sse-connect
# ---------------------------------------------------------------------------


class TestSSESelfSwap:
    """ERROR when sse-swap is on the same element as sse-connect."""

    def test_error_when_sse_swap_on_sse_connect(self):
        template_sources = {
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/stream" '
                'sse-swap="fragment" hx-swap="beforeend">'
                "</div>"
            ),
        }
        issues = _check_sse_self_swap(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "sse_self_swap"
        assert "querySelectorAll" in issues[0].message
        assert 'sse-swap="fragment"' in issues[0].message

    def test_no_error_when_sse_swap_on_child(self):
        template_sources = {
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/stream">'
                '<span sse-swap="fragment" hx-swap="beforeend"></span>'
                "</div>"
            ),
        }
        issues = _check_sse_self_swap(template_sources)
        assert issues == []

    def test_no_error_for_sse_connect_without_swap(self):
        template_sources = {
            "page.html": '<div hx-ext="sse" sse-connect="/events"></div>',
        }
        issues = _check_sse_self_swap(template_sources)
        assert issues == []


# ---------------------------------------------------------------------------
# SSE scope check — sse-connect inside broad hx-target without hx-disinherit
# ---------------------------------------------------------------------------


class TestSSEConnectScope:
    """WARN when sse-connect is inside broad hx-target without hx-disinherit."""

    def test_warns_without_disinherit(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "editor.html": (
                '<div hx-ext="sse" sse-connect="/doc/123/stream">'
                '<span id="status" sse-swap="status">ok</span>'
                "</div>"
            ),
        }
        broad = _collect_broad_targets(template_sources)
        issues = _check_sse_connect_scope(template_sources, broad)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "sse_scope"
        assert "hx-disinherit" in issues[0].message or "sse_scope" in issues[0].message

    def test_no_warning_with_disinherit(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "editor.html": (
                '<div hx-ext="sse" sse-connect="/doc/123/stream" '
                'hx-disinherit="hx-target hx-swap">'
                '<span id="status" sse-swap="status">ok</span>'
                "</div>"
            ),
        }
        broad = _collect_broad_targets(template_sources)
        issues = _check_sse_connect_scope(template_sources, broad)
        assert issues == []

    def test_no_warning_when_no_broad_targets(self):
        template_sources = {
            "page.html": (
                '<div hx-ext="sse" sse-connect="/events">'
                '<span sse-swap="status"></span>'
                "</div>"
            ),
        }
        broad = _collect_broad_targets(template_sources)
        assert broad == set()
        issues = _check_sse_connect_scope(template_sources, broad)
        assert issues == []


# ---------------------------------------------------------------------------
# SSE event cross-reference — sse-swap vs SSEContract.event_types
# ---------------------------------------------------------------------------


class TestSSEEventCrossref:
    """Cross-reference sse-swap values against SSEContract.event_types."""

    def test_warns_for_undeclared_sse_swap(self, tmp_path):
        """sse-swap listens for event not in SSEContract.event_types."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/stream">'
            '<span sse-swap="status">ok</span>'
            '<span sse-swap="typo_event">x</span>'
            "</div>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/stream")
        @contract(returns=SSEContract(
            event_types=frozenset({"status", "presence"}),
        ))
        async def stream():
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        # typo_event is undeclared (WARNING)
        warnings = [i for i in crossref if i.severity == Severity.WARNING]
        assert len(warnings) == 1
        assert "typo_event" in warnings[0].message

        # presence is declared but has no sse-swap (INFO)
        infos = [i for i in crossref if i.severity == Severity.INFO]
        assert len(infos) == 1
        assert "presence" in infos[0].message

    def test_no_issues_when_events_match(self, tmp_path):
        """All sse-swap values match declared event_types."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/stream">'
            '<span sse-swap="status">ok</span>'
            '<span sse-swap="presence">0</span>'
            "</div>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/stream")
        @contract(returns=SSEContract(
            event_types=frozenset({"status", "presence"}),
        ))
        async def stream():
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        assert crossref == []

    def test_skipped_when_no_event_types_declared(self, tmp_path):
        """SSEContract without event_types -> no cross-reference."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/stream">'
            '<span sse-swap="whatever">x</span>'
            "</div>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/stream")
        @contract(returns=SSEContract())
        async def stream():
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        assert crossref == []

    def test_handles_jinja_urls(self, tmp_path):
        """sse-connect with Jinja expressions should match parameterized routes."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/doc/{{ doc.id }}/stream">'
            '<span sse-swap="status">ok</span>'
            "</div>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/doc/{doc_id}/stream")
        @contract(returns=SSEContract(
            event_types=frozenset({"status", "title"}),
        ))
        async def stream(doc_id: str):
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        # title is declared but has no sse-swap (INFO)
        infos = [i for i in crossref if i.severity == Severity.INFO]
        assert len(infos) == 1
        assert "title" in infos[0].message
