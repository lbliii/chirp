"""Tests for chirp.contracts — typed hypermedia contract validation."""

from chirp.app import App
from chirp.config import AppConfig
from chirp.contracts import (
    CheckResult,
    ContractIssue,
    FragmentContract,
    RouteContract,
    SSEContract,
    Severity,
    _attr_to_method,
    _check_accessibility,
    _extract_targets_from_source,
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
        assert "No errors" in summary

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
        assert "test.html" == issues[0].template

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


class TestCheckHypermediaSurface:
    """Integration test for the full hypermedia check."""

    def test_app_with_no_routes(self, tmp_path):
        app = App(AppConfig(template_dir=str(tmp_path)))
        result = check_hypermedia_surface(app)
        assert result.routes_checked == 0

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
