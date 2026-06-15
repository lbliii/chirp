"""Integration tests: custom contract checks with mounted pages and chirp-ui."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.app.state import ContractCheckSnapshot
from chirp.contracts import CheckResult, ContractIssue, Severity, check_hypermedia_surface


class TestMountedPagesWithCustomCheck:
    """Custom checks work alongside built-in checks in a mounted-pages app."""

    def test_custom_check_runs_with_mounted_pages(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        (pages_dir / "page.py").write_text("def get(): return {}")
        (pages_dir / "page.html").write_text("<html><body>hello</body></html>")

        app = App(AppConfig(template_dir=str(pages_dir), debug=True))
        app.mount_pages(str(pages_dir))

        seen_templates: dict[str, str] = {}

        def audit_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            seen_templates.update(snapshot.template_sources)
            result.issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="audit",
                    message="Audit check ran.",
                )
            )

        app.register_contract_check(audit_check)
        result = check_hypermedia_surface(app)

        # Custom check ran and produced its issue
        audit_issues = [i for i in result.issues if i.category == "audit"]
        assert len(audit_issues) == 1

        # Custom check received template sources from the mounted pages
        assert "page.html" in seen_templates

        # Built-in checks also ran (routes were checked)
        assert result.routes_checked >= 1

    def test_custom_check_with_extras_and_mounted_pages(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        (pages_dir / "page.py").write_text("def get(): return {}")
        (pages_dir / "page.html").write_text(
            "<html><body>{% block content %}hi{% end %}</body></html>"
        )

        app = App(AppConfig(template_dir=str(pages_dir), debug=True))
        app.mount_pages(str(pages_dir))

        required_blocks = {"content"}
        app.set_contract_check_data("required_blocks", required_blocks)

        def block_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            required: set[str] = snapshot.extras.get("required_blocks", set())
            for name, source in snapshot.template_sources.items():
                for block in required:
                    if f"{{% block {block} %}}" not in source:
                        result.issues.append(
                            ContractIssue(
                                severity=Severity.WARNING,
                                category="block_check",
                                message=f"Missing required block '{block}'",
                                template=name,
                            )
                        )

        app.register_contract_check(block_check)
        result = check_hypermedia_surface(app)

        # page.html has {% block content %}, so no warnings from it
        block_issues = [
            i for i in result.issues if i.category == "block_check" and i.template == "page.html"
        ]
        assert len(block_issues) == 0

    def test_failing_custom_check_does_not_break_builtins(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        (pages_dir / "page.py").write_text("def get(): return {}")
        (pages_dir / "page.html").write_text("<html><body>ok</body></html>")

        # debug=False to avoid the debug check runner calling sys.exit(1)
        # on the intentional ERROR from the crashing check.
        app = App(AppConfig(template_dir=str(pages_dir)))
        app.mount_pages(str(pages_dir))

        def crashing_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            msg = "Integration crash"
            raise RuntimeError(msg)

        app.register_contract_check(crashing_check)
        result = check_hypermedia_surface(app)

        # The crash was captured as an ERROR issue
        errors = [i for i in result.issues if i.category == "plugin_check_error"]
        assert len(errors) == 1
        assert "crashing_check" in errors[0].message

        # Built-in checks still ran
        assert result.routes_checked >= 1


class TestChirpUIContractCheck:
    """The chirp-ui contract check catches invalid component imports."""

    def test_chirpui_import_without_use_chirp_ui_gets_runtime_hint(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(
            '{% from "chirpui/card.html" import card %}<html>{{ card() }}</html>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        result = check_hypermedia_surface(app)
        runtime_issues = [i for i in result.issues if i.category == "chirpui_runtime"]
        assert len(runtime_issues) == 1
        assert runtime_issues[0].severity == Severity.INFO
        assert "use_chirp_ui(app)" in runtime_issues[0].message

    def test_use_chirp_ui_reports_manifest_stats(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(
            '{% from "chirpui/card.html" import card %}<html>{{ card() }}</html>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.ext.chirp_ui import use_chirp_ui

        use_chirp_ui(app)
        result = check_hypermedia_surface(app)
        messages = [i.message for i in result.issues if i.category == "design_system"]
        assert any("chirpui-manifest@" in msg for msg in messages)
        assert any("requirements:" in msg for msg in messages)

    def test_valid_import_no_issues(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(
            '{% from "chirpui/card.html" import card %}<html>{{ card() }}</html>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.ext.chirp_ui import use_chirp_ui

        use_chirp_ui(app)
        result = check_hypermedia_surface(app)
        import_issues = [i for i in result.issues if i.category == "chirpui_import"]
        assert len(import_issues) == 0

    def test_typo_import_produces_error(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(
            '{% from "chirpui/cardd.html" import card %}<html>{{ card() }}</html>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.ext.chirp_ui import use_chirp_ui

        use_chirp_ui(app)
        result = check_hypermedia_surface(app)
        import_issues = [i for i in result.issues if i.category == "chirpui_import"]
        assert len(import_issues) == 1
        assert "cardd.html" in import_issues[0].message
        assert import_issues[0].template == "page.html"
        assert import_issues[0].severity == Severity.ERROR

    def test_multiple_typos_across_templates(self, tmp_path: Path) -> None:
        (tmp_path / "a.html").write_text('{% from "chirpui/modall.html" import modal %}<div></div>')
        (tmp_path / "b.html").write_text('{% from "chirpui/bttun.html" import btn %}<div></div>')
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.ext.chirp_ui import use_chirp_ui

        use_chirp_ui(app)
        result = check_hypermedia_surface(app)
        import_issues = [i for i in result.issues if i.category == "chirpui_import"]
        assert len(import_issues) == 2
        templates_with_issues = {i.template for i in import_issues}
        assert "a.html" in templates_with_issues
        assert "b.html" in templates_with_issues

    def test_mixed_valid_and_invalid_imports(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text(
            '{% from "chirpui/card.html" import card %}\n'
            '{% from "chirpui/nonexist.html" import thing %}\n'
            "<html>{{ card() }}</html>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.ext.chirp_ui import use_chirp_ui

        use_chirp_ui(app)
        result = check_hypermedia_surface(app)
        import_issues = [i for i in result.issues if i.category == "chirpui_import"]
        assert len(import_issues) == 1
        assert "nonexist.html" in import_issues[0].message


class TestChirpUICSPContractCheck:
    """The built-in chirpui_csp check fires through the full app.check() path (#233).

    It must be a built-in (not a plugin check) because it reads config +
    middleware_list, which the plugin ContractCheckSnapshot does not expose. These
    tests drive it via check_hypermedia_surface so the wiring in checker.py is
    exercised, not just the rule in isolation.
    """

    @pytest.mark.issue(233)
    def test_conflicting_static_csp_fires_in_deploy_posture(self, tmp_path: Path) -> None:
        """chirp-ui active + a static CSP that forbids Alpine's needs -> ERROR
        under deploy (production) posture, even with csp_nonce_enabled on."""
        (tmp_path / "page.html").write_text(
            '{% from "chirpui/card.html" import card %}<html>{{ card() }}</html>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.ext.chirp_ui import use_chirp_ui
        from chirp.middleware.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        use_chirp_ui(app)
        app.add_middleware(
            SecurityHeadersMiddleware(
                SecurityHeadersConfig(
                    content_security_policy="default-src 'self'; script-src 'self'"
                )
            )
        )
        result = check_hypermedia_surface(app, deploy=True)
        csp_issues = [i for i in result.issues if i.category == "chirpui_csp"]
        assert len(csp_issues) == 1
        assert csp_issues[0].severity == Severity.ERROR

    @pytest.mark.issue(233)
    def test_stock_chirpui_app_is_silent(self, tmp_path: Path) -> None:
        """The auto-wired chirp-ui path passes — no chirpui_csp issue even in
        deploy (production) posture."""
        (tmp_path / "page.html").write_text(
            '{% from "chirpui/card.html" import card %}<html>{{ card() }}</html>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.ext.chirp_ui import use_chirp_ui

        use_chirp_ui(app)
        result = check_hypermedia_surface(app, deploy=True)
        csp_issues = [i for i in result.issues if i.category == "chirpui_csp"]
        assert csp_issues == []

    @pytest.mark.issue(233)
    def test_non_chirpui_app_unaffected(self, tmp_path: Path) -> None:
        """A non-chirp-ui app never trips chirpui_csp, even with a restrictive CSP."""
        (tmp_path / "page.html").write_text("<html><body>hi</body></html>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        from chirp.middleware.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        app.add_middleware(
            SecurityHeadersMiddleware(
                SecurityHeadersConfig(
                    content_security_policy="default-src 'self'; script-src 'self'"
                )
            )
        )
        result = check_hypermedia_surface(app, deploy=True)
        csp_issues = [i for i in result.issues if i.category == "chirpui_csp"]
        assert csp_issues == []
