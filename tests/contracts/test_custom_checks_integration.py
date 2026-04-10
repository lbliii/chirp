"""Integration tests: custom contract checks with mounted pages and chirp-ui."""

from pathlib import Path

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
