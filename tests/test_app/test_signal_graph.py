"""Regression proof for the private freeze-compiled signal graph."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from chirp.app import App
from chirp.app._signal_graph import _SignalGraph, _SignalProducerNode
from chirp.app.hypermedia_program import SourceOrigin, stable_identity
from chirp.config import AppConfig
from chirp.errors import ConfigurationError


def _attempt_mutation(value: object, attribute: str, replacement: object) -> None:
    setattr(value, attribute, replacement)


def _build_signal_app(tmp_path) -> App:
    (tmp_path / "base.html").write_text(
        "<main {{ signal_connect() }}>{% block content %}{% endblock %}</main>",
        encoding="utf-8",
    )
    (tmp_path / "page.html").write_text(
        '{% extends "base.html" %}{% block content %}'
        "{{ signal('shown') }}{{ signal_bind('shown') }}"
        "{{ signal(topic_name) }}{{ signal('misspelled') }}"
        "{% endblock %}",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))
    app.route("/", template="page.html")(lambda: "ok")
    # Page discovery normally records both the leaf and its composed layouts.
    app._mutable_state.page_templates.update({"base.html", "page.html"})
    app._mutable_state.page_leaf_templates.add("page.html")

    @app.signal("source", audience="session", coalesce=False)
    async def source():
        if False:
            yield None

    @app.derived("shown", on=("source",))
    def shown(value):
        return value

    return app


class _MountedSignalPlugin:
    def register(self, app: App, prefix: str) -> None:
        @app.signal("plugin_status")
        async def plugin_status():
            if False:
                yield None

        app.route(prefix, template="plugin.html")(lambda: "ok")


@pytest.mark.issue(683)
def test_graph_compiles_producers_dependencies_sinks_and_composed_owner(tmp_path) -> None:
    app = _build_signal_app(tmp_path)
    app.freeze()

    graph = app._runtime_state._signal_graph
    assert graph is not None
    assert [(node.name, node.kind) for node in graph.producers] == [
        ("shown", "derived"),
        ("source", "primary"),
    ]
    source = graph.producer("source")
    shown = graph.producer("shown")
    assert source is not None
    assert shown is not None
    assert (source.source_kind, source.audience, source.coalesce) == ("lazy", "session", False)
    assert (shown.dependencies, shown.audience) == (("source",), "session")

    shown_bindings = [node for node in graph.bindings if node.signal_name == "shown"]
    assert len(shown_bindings) == 2
    assert all(node.ownership == "resolved" for node in graph.bindings)
    assert len(graph.connections) == 1
    assert graph.connections[0].template_id == stable_identity("template", "base.html")
    assert graph.sink_ids_for("source") == tuple(sorted(node.id for node in shown_bindings))

    edge_shapes = {(edge.kind, edge.resolved) for edge in graph.edges}
    assert ("depends_on", True) in edge_shapes
    assert ("renders_to", False) in edge_shapes
    assert ("owned_by", True) in edge_shapes
    assert ("activates", True) in edge_shapes


@pytest.mark.issue(683)
def test_dynamic_signal_name_stays_unknown_and_multiple_bindings_remain_distinct(tmp_path) -> None:
    app = _build_signal_app(tmp_path)
    app.freeze()
    graph = app._runtime_state._signal_graph
    assert graph is not None

    dynamic = [node for node in graph.bindings if node.evidence == "dynamic"]
    assert len(dynamic) == 1
    assert dynamic[0].signal_name is None
    assert dynamic[0].ownership == "resolved"
    assert len({node.id for node in graph.bindings}) == len(graph.bindings)


@pytest.mark.issue(683)
def test_plugin_mounted_template_and_producer_compile_into_same_graph(tmp_path) -> None:
    (tmp_path / "plugin.html").write_text(
        "<main {{ signal_connect() }}>{{ signal('plugin_status') }}</main>",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=tmp_path))
    app.mount("/plugin", _MountedSignalPlugin())

    app.freeze()
    graph = app._runtime_state._signal_graph
    assert graph is not None
    producer = graph.producer("plugin_status")
    assert producer is not None
    assert len(graph.sink_ids_for("plugin_status")) == 1
    binding = next(node for node in graph.bindings if node.signal_name == "plugin_status")
    assert binding.ownership == "resolved"


@pytest.mark.issue(683)
def test_equivalent_graphs_have_stable_identity_digest_and_immutable_reads(tmp_path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _build_signal_app(first_dir)
    second = _build_signal_app(second_dir)
    first.freeze()
    second.freeze()
    first_graph = first._runtime_state._signal_graph
    second_graph = second._runtime_state._signal_graph
    assert first_graph is not None
    assert second_graph is not None

    assert first_graph == second_graph
    assert first_graph.topology_digest == second_graph.topology_digest
    with pytest.raises(FrozenInstanceError):
        _attempt_mutation(first_graph, "edges", ())
    with ThreadPoolExecutor(max_workers=16) as pool:
        receipts = tuple(pool.map(lambda _: first_graph.topology_digest, range(64)))
    assert set(receipts) == {first_graph.topology_digest}


@pytest.mark.issue(683)
def test_duplicate_graph_identity_fails_loud() -> None:
    producer = _SignalProducerNode(
        id=stable_identity("signal_producer", "duplicate"),
        name="duplicate",
        kind="primary",
        source_kind="push",
        dependencies=(),
        audience="global",
        coalesce=True,
        origin=SourceOrigin("registry", "duplicate"),
    )

    with pytest.raises(ConfigurationError, match="Duplicate signal graph producer identity"):
        _SignalGraph(producers=(producer, producer))


@pytest.mark.issue(683)
def test_late_registration_remains_rejected_by_freeze_boundary(tmp_path) -> None:
    app = _build_signal_app(tmp_path)
    app.freeze()

    with pytest.raises(RuntimeError, match="Cannot modify the app"):

        @app.signal("late")
        async def late():
            if False:
                yield None
