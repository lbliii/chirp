"""Tests for dead template detection in check_hypermedia_surface."""

import pytest
from kida import ChoiceLoader, Environment, FileSystemLoader

from chirp import App, Page
from chirp.app.state import ContractCheckSnapshot
from chirp.config import AppConfig
from chirp.contracts import (
    CheckResult,
    ContractIssue,
    FragmentContract,
    Severity,
    check_hypermedia_surface,
    contract,
    rules_chirpui_css_verify,
)


def _user_dead(result: CheckResult) -> list[ContractIssue]:
    """Filter dead-template issues to only user templates (not built-in)."""

    def is_builtin(tmpl: str | None) -> bool:
        if not tmpl:
            return True
        return tmpl.startswith(("chirp/", "chirpui", "themes/"))

    return [i for i in result.issues if i.category == "dead" and not is_builtin(i.template)]


class TestDeadTemplateDetection:
    """Integration tests for dead template detection in check_hypermedia_surface."""

    def test_unreferenced_template_reported(self, tmp_path):
        """An unused template should be reported as dead."""
        (tmp_path / "index.html").write_text("{% block content %}<h1>Home</h1>{% endblock %}")
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
        assert dead[0].severity == Severity.WARNING

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

    def test_relative_included_template_not_dead(self, tmp_path):
        """Kida 0.8 relative include references should be resolved before dead checks."""
        pages = tmp_path / "pages"
        pages.mkdir()
        (pages / "index.html").write_text(
            '{% block content %}{% include "./_card.html" %}{% endblock %}'
        )
        (pages / "_card.html").write_text("<article>card</article>")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        @contract(returns=FragmentContract("pages/index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_alias_included_template_not_dead(self, tmp_path):
        """Kida 0.8 alias references should resolve when the custom env exposes aliases."""
        components = tmp_path / "components"
        components.mkdir()
        (tmp_path / "index.html").write_text(
            '{% block content %}{% include "@components/card.html" %}{% endblock %}'
        )
        (components / "card.html").write_text("<article>card</article>")
        env = Environment(
            loader=FileSystemLoader(str(tmp_path)),
            template_aliases={"components": "components"},
        )
        app = App(AppConfig(template_dir=str(tmp_path)), kida_env=env)

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_extended_template_not_dead(self, tmp_path):
        """A template referenced via extends should not be reported."""
        (tmp_path / "base.html").write_text("{% block content %}{% endblock %}")
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
        (tmp_path / "index.html").write_text("{% block content %}<h1>Home</h1>{% endblock %}")
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
        (tmp_path / "search.html").write_text("{% block results %}results{% endblock %}")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/search")
        @contract(returns=FragmentContract("search.html", "results"))
        async def search():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    def test_page_return_template_not_dead(self, tmp_path):
        """Page(\"*.html\", ...) in a route handler should count as a template reference."""
        (tmp_path / "oops.html").write_text("{% block content %}oops{% endblock %}")
        (tmp_path / "index.html").write_text("{% block content %}ok{% endblock %}")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/oops", referenced=True)
        def oops():
            return Page("oops.html", "content", title="x")

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        dead = _user_dead(result)
        assert len(dead) == 0

    @pytest.mark.issue(237)
    def test_python_module_template_constant_not_dead(self, tmp_path):
        """Module-level template constants and helper Fragment() calls count."""
        (tmp_path / "index.html").write_text("{% block content %}ok{% endblock %}")
        (tmp_path / "toast_oob.html").write_text("<div>{% block toast %}{% endblock %}</div>")
        app_py = tmp_path / "app_module.py"
        app_py.write_text(
            f'''
from chirp import App, Fragment
from chirp.config import AppConfig
from chirp.contracts import FragmentContract, contract

_TOAST_TEMPLATE = "toast_oob.html"

def _toast(message: str) -> Fragment:
    return Fragment(_TOAST_TEMPLATE, "toast", message=message)

app = App(AppConfig(template_dir=r"{tmp_path}"))

@app.route("/")
@contract(returns=FragmentContract("index.html", "content"))
async def home():
    return _toast("hi")
'''
        )
        import importlib.util

        spec = importlib.util.spec_from_file_location("dead_template_helper_app", app_py)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        import sys

        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        result = check_hypermedia_surface(module.app)
        dead = _user_dead(result)
        assert len(dead) == 0

    @pytest.mark.issue(707)
    @pytest.mark.parametrize(
        ("referenced_name", "canonical_name"),
        [
            ("partials/x.html", "partials/x.html"),
            ("templates/partials/x.html", "templates/partials/x.html"),
        ],
    )
    def test_nested_choice_loader_scans_aliases_once_and_preserves_custom_snapshot(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        referenced_name: str,
        canonical_name: str,
    ) -> None:
        nested = tmp_path / "templates" / "partials"
        nested.mkdir(parents=True)
        (nested / "x.html").write_text(
            '{% block content %}<div class="chirpui-alias-typo">x</div>{% endblock %}',
            encoding="utf-8",
        )
        env = Environment(
            loader=ChoiceLoader(
                [FileSystemLoader(tmp_path), FileSystemLoader(tmp_path / "templates")]
            )
        )
        app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)), kida_env=env)
        app.set_contract_check_data("chirpui_components", frozenset({"card.html"}))
        monkeypatch.setattr(
            rules_chirpui_css_verify,
            "_known_chirpui_css_classes",
            lambda: frozenset({"chirpui-known"}),
        )
        custom_names: set[str] = set()

        def capture_snapshot(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            custom_names.update(snapshot.template_sources)

        app.register_contract_check(capture_snapshot)

        @app.route("/")
        @contract(returns=FragmentContract(referenced_name, "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)
        css_issues = [issue for issue in result.issues if issue.category == "chirpui_css_verify"]

        assert _user_dead(result) == []
        assert result.templates_scanned == 1
        assert len(css_issues) == 1
        assert css_issues[0].template == canonical_name
        assert css_issues[0].details is not None
        assert "partials/x.html" in css_issues[0].details
        assert "templates/partials/x.html" in css_issues[0].details
        assert custom_names == {"partials/x.html", "templates/partials/x.html"}

    @pytest.mark.issue(707)
    def test_declared_template_alias_normalizes_before_dead_comparison(self, tmp_path) -> None:
        nested = tmp_path / "templates" / "partials"
        nested.mkdir(parents=True)
        (nested / "x.html").write_text(
            "{% block content %}declared{% endblock %}", encoding="utf-8"
        )
        env = Environment(
            loader=ChoiceLoader(
                [FileSystemLoader(tmp_path), FileSystemLoader(tmp_path / "templates")]
            )
        )
        app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)), kida_env=env)
        app.declare_template("templates/partials/x.html", blocks=("content",))

        @app.route("/")
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)

        assert _user_dead(result) == []
        assert result.templates_scanned == 1

    @pytest.mark.issue(707)
    def test_template_reference_alias_normalizes_before_dead_comparison(self, tmp_path) -> None:
        nested = tmp_path / "templates" / "partials"
        nested.mkdir(parents=True)
        (nested / "x.html").write_text("<div>included</div>", encoding="utf-8")
        (tmp_path / "index.html").write_text(
            '{% block content %}{% include "templates/partials/x.html" %}{% endblock %}',
            encoding="utf-8",
        )
        env = Environment(
            loader=ChoiceLoader(
                [FileSystemLoader(tmp_path), FileSystemLoader(tmp_path / "templates")]
            )
        )
        app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)), kida_env=env)

        @app.route("/")
        @contract(returns=FragmentContract("index.html", "content"))
        async def home():
            return "ok"

        result = check_hypermedia_surface(app)

        assert _user_dead(result) == []
        assert result.templates_scanned == 2
