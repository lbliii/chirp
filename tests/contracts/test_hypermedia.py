"""Integration tests for the full hypermedia check."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.template_scan import extract_targets_from_source
from tests.helpers.contract_fixtures import write_layout_page


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
            "chirp.contracts.checker._route_path_has_flask_syntax", fake_has_flask_syntax
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
        (tmp_path / "index.html").write_text('<div hx-get="/api/missing">load</div>')
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        assert not result.ok
        assert any("no matching route" in i.message for i in result.errors)

    def test_attrs_map_reference_counts_for_orphan_detection(self, tmp_path):
        (tmp_path / "index.html").write_text(
            '{{ form("/x", method="post", attrs_map={"hx-post": "/config/set"}) }}'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        async def home():
            return "ok"

        @app.route("/config/set", methods=["POST"])
        async def config_set():
            return "ok"

        result = check_hypermedia_surface(app)
        orphan_issues = [
            i for i in result.issues if i.category == "orphan" and i.route == "/config/set"
        ]
        assert orphan_issues == []

    def test_detects_method_mismatch(self, tmp_path):
        """Template uses hx-post but route only allows GET."""
        (tmp_path / "index.html").write_text('<button hx-post="/api/items">submit</button>')
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items")  # GET only
        async def list_items():
            return "ok"

        result = check_hypermedia_surface(app)
        assert not result.ok
        assert any("POST" in i.message and "GET" in i.message for i in result.errors)

    def test_detects_invalid_hx_selector_syntax(self, tmp_path):
        (tmp_path / "index.html").write_text(
            '<button hx-post="/api/items" hx-target="\'#result\'">go</button>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/api/items", methods=["POST"])
        async def create_item():
            return "ok"

        result = check_hypermedia_surface(app)
        selector_errors = [i for i in result.errors if i.category == "selector_syntax"]
        assert len(selector_errors) == 1
        assert "wrapped in quotes" in selector_errors[0].message

    def test_valid_hx_targets(self, tmp_path):
        """All htmx targets match registered routes."""
        (tmp_path / "index.html").write_text(
            '<div hx-get="/api/items">load</div><button hx-post="/api/items">add</button>'
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

    def test_confirm_url_counts_as_route_reference(self, tmp_path):
        (tmp_path / "index.html").write_text(
            '{{ confirm_dialog("del", confirm_url="/items/1", confirm_method="DELETE") }}'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/items/{item_id}", methods=["DELETE"])
        async def delete_item():
            return "ok"

        result = check_hypermedia_surface(app)
        route_errors = [issue for issue in result.errors if issue.category == "target"]
        assert route_errors == []
        assert ("confirm_url", "/items/1", "DELETE") in extract_targets_from_source(
            (tmp_path / "index.html").read_text()
        )

    def test_legacy_action_contract_warns_without_route_error(self, tmp_path):
        (tmp_path / "index.html").write_text('{{ btn("Update", action="update-collection") }}')
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/collections/update", methods=["POST"])
        async def update_collection():
            return "ok"

        result = check_hypermedia_surface(app)
        route_errors = [issue for issue in result.errors if "no matching route" in issue.message]
        assert route_errors == []
        contract_warnings = [
            issue for issue in result.warnings if issue.category == "template_contract"
        ]
        assert len(contract_warnings) == 1
        assert "legacy component contract" in contract_warnings[0].message

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
        route_errors = [i for i in result.errors if "no matching route" in i.message]
        assert not route_errors, (
            f"Expected no 'has no matching route' errors for URLs with query params, "
            f"got: {[e.message for e in route_errors]}"
        )
        assert result.targets_found >= 2

    def test_accessibility_warnings_in_surface_check(self, tmp_path):
        """Accessibility warnings surface through the full check."""
        (tmp_path / "index.html").write_text(
            '<div hx-get="/api/items">load</div><button hx-post="/api/items">add</button>'
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
        a11y_warnings = [i for i in result.warnings if i.category == "accessibility"]
        assert len(a11y_warnings) == 1
        assert "<div>" in a11y_warnings[0].message

    def test_no_accessibility_warnings_when_all_interactive(self, tmp_path):
        """No a11y warnings when all htmx attrs are on interactive elements."""
        (tmp_path / "index.html").write_text(
            '<a hx-get="/api/items">load</a><button hx-post="/api/items">add</button>'
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
        a11y_warnings = [i for i in result.warnings if i.category == "accessibility"]
        assert len(a11y_warnings) == 0

    def test_swap_safety_warning_surfaces(self, tmp_path):
        """Broad hx-target + mutating request without local target warns."""
        write_layout_page(
            tmp_path,
            '<body hx-boost="true" hx-target="#app-content">{% block content %}{% endblock %}</body>',
            "{% block content %}"
            '<form hx-post="/docs/new"><button>Create</button></form>'
            "{% endblock %}",
            page_name="index.html",
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/docs/new", methods=["POST"])
        async def create_doc():
            return "ok"

        result = check_hypermedia_surface(app)
        swap_warnings = [issue for issue in result.warnings if issue.category == "swap_safety"]
        assert len(swap_warnings) == 1
        assert "Action()" in swap_warnings[0].message
