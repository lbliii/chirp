"""End-to-end proof for dynamic template reachability declarations (#498)."""

from dataclasses import FrozenInstanceError

import pytest

from chirp import App, AppConfig
from chirp.contracts import Severity, check_hypermedia_surface
from chirp.errors import ConfigurationError


def _dead_templates(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {
        issue.template
        for issue in result.issues
        if issue.category == "dead" and issue.template is not None
    }


@pytest.mark.issue(498)
def test_registry_driven_template_needs_no_unreachable_reference_stub(tmp_path) -> None:
    (tmp_path / "dynamic.html").write_text(
        "{% block results %}registry result{% endblock %}",
        encoding="utf-8",
    )
    (tmp_path / "truly_unused.html").write_text("old", encoding="utf-8")

    baseline = App(AppConfig(template_dir=tmp_path))

    @baseline.route("/")
    def baseline_home() -> str:
        return "ok"

    assert "dynamic.html" in _dead_templates(check_hypermedia_surface(baseline))

    app = App(AppConfig(template_dir=tmp_path))

    # A real registry can import this value from another module. The handler does
    # not need an unreachable return-type reference for source analysis.
    registry_template = "dynamic" + ".html"
    app.declare_template(registry_template, blocks=("results",))

    @app.route("/")
    def home() -> str:
        return "ok"

    result = check_hypermedia_surface(app)

    assert not [issue for issue in result.errors if issue.category == "template_declaration"]
    assert "dynamic.html" not in _dead_templates(result)
    assert "truly_unused.html" in _dead_templates(result)

    program = app._runtime_state.hypermedia_program
    assert program is not None
    assert program.declared_template_names == frozenset({"dynamic.html"})
    declaration = program.template_declarations[0]
    assert declaration.blocks == ("results",)
    assert declaration.origin.kind == "registry"
    assert declaration.origin.identifier.endswith(
        ":test_registry_driven_template_needs_no_unreachable_reference_stub"
    )
    assert declaration.origin.line is not None
    assert str(tmp_path) not in declaration.origin.identifier

    with pytest.raises(FrozenInstanceError):
        declaration.template = "other.html"  # type: ignore[misc]


@pytest.mark.issue(498)
def test_unknown_declared_template_is_actionable_error_with_origin(tmp_path) -> None:
    app = App(AppConfig(template_dir=tmp_path))
    app.declare_template("missing.html", blocks=("content",))

    result = check_hypermedia_surface(app)
    issues = [issue for issue in result.errors if issue.category == "template_declaration"]

    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.ERROR
    assert issue.template == "missing.html"
    assert "could not be loaded" in issue.message
    assert "test_unknown_declared_template_is_actionable_error_with_origin" in issue.message
    assert issue.details is not None
    assert "Declaration origin:" in issue.details


@pytest.mark.issue(498)
def test_declared_template_load_error_preserves_loader_details(tmp_path) -> None:
    (tmp_path / "broken.html").write_text("{% block", encoding="utf-8")
    app = App(AppConfig(template_dir=tmp_path))
    app.declare_template("broken.html")

    result = check_hypermedia_surface(app)
    issue = next(issue for issue in result.errors if issue.category == "template_declaration")
    program = app._runtime_state.hypermedia_program
    assert program is not None
    template = program.template("broken.html")
    assert template is not None
    assert template.load_error is not None
    assert template.load_error in issue.message


@pytest.mark.issue(498)
def test_unknown_declared_block_lists_available_blocks(tmp_path) -> None:
    (tmp_path / "search.html").write_text(
        "{% block results %}ok{% endblock %}",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))
    app.declare_template("search.html", blocks=("resutls",))

    result = check_hypermedia_surface(app)
    issues = [issue for issue in result.errors if issue.category == "template_declaration"]

    assert len(issues) == 1
    assert "'resutls' does not exist" in issues[0].message
    assert "Available blocks: results" in issues[0].message
    assert "test_unknown_declared_block_lists_available_blocks" in issues[0].message


@pytest.mark.issue(498)
def test_declaration_is_setup_only_and_validates_names(tmp_path) -> None:
    app = App(AppConfig(template_dir=tmp_path))

    with pytest.raises(ConfigurationError, match="cannot be empty"):
        app.declare_template(" ")
    with pytest.raises(TypeError, match="not a string"):
        app.declare_template("page.html", blocks="content")
    with pytest.raises(TypeError, match="block names must be strings"):
        app.declare_template("page.html", blocks=(1,))  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match=r"block name.*cannot be empty"):
        app.declare_template("page.html", blocks=("",))

    app.freeze()
    with pytest.raises(RuntimeError, match="Cannot modify"):
        app.declare_template("late.html")


@pytest.mark.issue(498)
def test_duplicate_blocks_and_exact_declarations_compile_once(tmp_path) -> None:
    (tmp_path / "page.html").write_text(
        "{% block alpha %}{% endblock %}{% block beta %}{% endblock %}",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))

    for _ in range(2):
        app.declare_template("page.html", blocks=("beta", "alpha", "beta"))
    app.freeze()

    program = app._runtime_state.hypermedia_program
    assert program is not None
    assert len(program.template_declarations) == 1
    assert all(item.blocks == ("alpha", "beta") for item in program.template_declarations)
