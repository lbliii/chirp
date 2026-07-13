"""Regression proof for the internal HypermediaProgram compiler."""

from dataclasses import FrozenInstanceError

import pytest

from chirp import App
from chirp.app.hypermedia_program import (
    EnhancementEdge,
    HypermediaProgram,
    RouteNode,
    SourceOrigin,
    stable_identity,
)
from chirp.config import AppConfig
from chirp.contracts import FragmentContract, check_hypermedia_surface, contract
from chirp.errors import ConfigurationError


def _index() -> str:
    return "ok"


def _projects() -> str:
    return "ok"


def _attempt_mutation(value: object, attribute: str, replacement: object) -> None:
    setattr(value, attribute, replacement)


def _build_equivalent_app(tmp_path, *, reverse: bool) -> App:
    (tmp_path / "index.html").write_text(
        "{% block page_root %}{% block content %}ok{% endblock %}{% endblock %}",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))
    registrations = [
        ("/", _index, "home"),
        ("/projects", _projects, "projects"),
    ]
    if reverse:
        registrations.reverse()
    for path, handler, name in registrations:
        app.route(path, name=name, template="index.html")(handler)
    app._mutable_state.page_templates.add("index.html")
    app._mutable_state.page_leaf_templates.add("index.html")
    app._mutable_state.fragment_target_registry.register(
        "main",
        fragment_block="page_root",
        required=True,
    )
    return app


@pytest.mark.issue(509)
def test_program_compiles_stable_route_template_block_target_graph(tmp_path) -> None:
    app = _build_equivalent_app(tmp_path, reverse=False)
    app.freeze()

    program = app._runtime_state.hypermedia_program
    assert program is not None
    assert stable_identity("route", "GET", "/projects") in {node.id for node in program.routes}
    assert program.template("index.html") is not None
    assert program.block_names("index.html") == frozenset({"content", "page_root"})
    assert {target.target_id for target in program.targets} == {"main"}

    transition_shapes = {
        (edge.kind, edge.source_id, edge.destination_id, edge.resolved)
        for edge in program.transitions
    }
    assert (
        "target_block",
        stable_identity("target", "main"),
        stable_identity("block", "index.html", "page_root"),
        True,
    ) in transition_shapes
    assert (
        "route_template",
        stable_identity("route", "GET", "/projects"),
        stable_identity("template", "index.html"),
        True,
    ) in transition_shapes


@pytest.mark.issue(509)
def test_template_free_app_does_not_compile_bundled_template_inventory() -> None:
    app = App()
    app.route("/")(_index)
    app.freeze()

    program = app._runtime_state.hypermedia_program
    assert program is not None
    assert program.templates == ()
    assert program.blocks == ()


@pytest.mark.issue(509)
def test_equivalent_registration_order_compiles_identical_program(tmp_path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _build_equivalent_app(first_dir, reverse=False)
    second = _build_equivalent_app(second_dir, reverse=True)

    first.freeze()
    second.freeze()

    assert first._runtime_state.hypermedia_program == second._runtime_state.hypermedia_program


@pytest.mark.issue(509)
def test_program_and_nodes_are_immutable_after_publication(tmp_path) -> None:
    app = _build_equivalent_app(tmp_path, reverse=False)
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None

    with pytest.raises(FrozenInstanceError):
        _attempt_mutation(program, "routes", ())
    with pytest.raises(FrozenInstanceError):
        _attempt_mutation(program.routes[0], "path", "/late")


@pytest.mark.issue(347)
def test_program_compiles_declared_enhancement_and_fallback_edge(tmp_path) -> None:
    (tmp_path / "chart.html").write_text(
        "{% block chart_table %}<table></table>{% endblock %}\n"
        '{% fragment chart_live enhancement="sse" fallback="chart_table" %}'
        "<svg></svg>{% endfragment %}",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))
    app.route("/chart", template="chart.html")(_index)

    app.freeze()

    program = app._runtime_state.hypermedia_program
    assert program is not None
    assert len(program.enhancements) == 1
    enhancement = program.enhancements[0]
    assert enhancement.template_id == stable_identity("template", "chart.html")
    assert enhancement.block_id == stable_identity("block", "chart.html", "chart_live")
    assert enhancement.capability == "sse"
    assert enhancement.fallback == "chart_table"
    assert enhancement.fallback_declared is True
    assert enhancement.origin == SourceOrigin("template", "chart.html:chart_live", 2)

    assert program.enhancement_edges == (
        EnhancementEdge(
            id=stable_identity(
                "enhancement_edge",
                stable_identity("block", "chart.html", "chart_live"),
                stable_identity("block", "chart.html", "chart_table"),
            ),
            enhanced_block_id=stable_identity("block", "chart.html", "chart_live"),
            fallback_block_id=stable_identity("block", "chart.html", "chart_table"),
            resolved=True,
            origin=SourceOrigin("template", "chart.html:chart_live", 2),
        ),
    )

    with pytest.raises(FrozenInstanceError):
        _attempt_mutation(enhancement, "capability", "htmx")


@pytest.mark.issue(347)
def test_program_preserves_unresolved_and_incomplete_enhancement_facts(tmp_path) -> None:
    (tmp_path / "chart.html").write_text(
        '{% fragment missing enhancement="future" fallback="not_there" %}'
        "missing{% endfragment %}"
        '{% fragment incomplete enhancement="sse" %}incomplete{% endfragment %}',
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))
    app.route("/chart", template="chart.html")(_index)

    app.freeze()

    program = app._runtime_state.hypermedia_program
    assert program is not None
    enhancements = {node.block_id: node for node in program.enhancements}
    missing_id = stable_identity("block", "chart.html", "missing")
    incomplete_id = stable_identity("block", "chart.html", "incomplete")
    assert enhancements[missing_id].capability == "future"
    assert enhancements[missing_id].fallback_declared is True
    assert enhancements[incomplete_id].fallback_declared is False
    assert enhancements[incomplete_id].fallback is None
    assert len(program.enhancement_edges) == 1
    assert program.enhancement_edges[0].enhanced_block_id == missing_id
    assert program.enhancement_edges[0].resolved is False


@pytest.mark.issue(347)
def test_ordinary_templates_compile_without_enhancement_facts(tmp_path) -> None:
    app = _build_equivalent_app(tmp_path, reverse=False)

    app.freeze()

    program = app._runtime_state.hypermedia_program
    assert program is not None
    assert program.enhancements == ()
    assert program.enhancement_edges == ()


@pytest.mark.issue(509)
def test_duplicate_route_identity_fails_during_compilation() -> None:
    route = RouteNode(
        id=stable_identity("route", "GET", "/duplicate"),
        path="/duplicate",
        method="GET",
        name=None,
        template_ids=(),
        origin=SourceOrigin("handler", "tests:duplicate"),
    )

    with pytest.raises(ConfigurationError, match="Duplicate hypermedia program route identity"):
        HypermediaProgram(routes=(route, route))


@pytest.mark.issue(509)
def test_unknown_declared_template_and_block_remain_actionable_errors(tmp_path) -> None:
    app = App(AppConfig(template_dir=tmp_path))

    @app.route("/missing")
    @contract(returns=FragmentContract("missing.html", "content"))
    def missing() -> str:
        return "not rendered"

    result = check_hypermedia_surface(app)
    program = app._runtime_state.hypermedia_program
    assert program is not None

    missing_template = program.template("missing.html")
    assert missing_template is not None
    assert missing_template.load_error is not None
    route_edges = [
        edge
        for edge in program.transitions
        if edge.source_id == stable_identity("route", "GET", "/missing")
    ]
    assert {edge.kind for edge in route_edges} == {"route_block", "route_template"}
    assert all(not edge.resolved for edge in route_edges)
    assert any(
        issue.category == "fragment"
        and issue.route == "/missing"
        and issue.template == "missing.html"
        for issue in result.errors
    )


@pytest.mark.issue(509)
def test_source_origins_are_semantic_and_public_safe(tmp_path) -> None:
    app = _build_equivalent_app(tmp_path, reverse=False)
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None

    route = next(node for node in program.routes if node.path == "/projects")
    template = program.template("index.html")
    target = next(node for node in program.targets if node.target_id == "main")
    assert route.origin.kind == "handler"
    assert route.origin.identifier.endswith(":_projects")
    assert str(tmp_path) not in route.origin.identifier
    assert template is not None
    assert template.origin.identifier == "index.html"
    assert target.origin.identifier == "main"
