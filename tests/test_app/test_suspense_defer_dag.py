"""Unit + freeze integration proof for Suspense compile-time defer DAGs (#948)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest
from kida import DictLoader, Environment

from chirp import App, AppConfig, Suspense
from chirp.app._suspense_dag import _SuspenseDeferDAG
from chirp.app.hypermedia_program import SourceOrigin, stable_identity
from chirp.errors import ConfigurationError
from chirp.templating.suspense import (
    DeferEdge,
    DeferExecutionPlan,
    plan_defer_execution,
)
from chirp.testing import TestClient

_INDEPENDENT_TEMPLATE = """\
<html><body>
<div id="stats">
{% block stats %}
  {% if stats is deferred %}<span class="skeleton">SKELETON-STATS</span>
  {% else %}<span>LOADED-STATS:{{ stats }}</span>{% end %}
{% end %}
</div>
<div id="feed">
{% block feed %}
  {% if feed is deferred %}<span class="skeleton">SKELETON-FEED</span>
  {% else %}<span>LOADED-FEED:{{ feed }}</span>{% end %}
{% end %}
</div>
</body></html>
"""

_COUPLED_TEMPLATE = """\
<html><body>
{% block panel %}
  {% if stats is deferred %}
    <span class="skeleton">SKELETON-PANEL</span>
  {% elif feed is deferred %}
    <span class="skeleton">SKELETON-PANEL</span>
  {% else %}
    <span>LOADED-PANEL:{{ stats }}|{{ feed }}</span>
  {% end %}
{% end %}
</body></html>
"""

_ANCESTOR_TEMPLATE = """\
<html><body>
{% block page_content %}
<h1>{{ title }}</h1>
<div id="hero_stars">
{% block hero_stars %}
  {% if stars is deferred %}<span class="skeleton">…</span>
  {% else %}<span>{{ stars }} stars</span>{% end %}
{% end %}
</div>
<div id="footer_stars">
{% block footer_stars %}
  {% if stars is deferred %}<span class="skeleton">…</span>
  {% else %}<span>{{ stars }} stars</span>{% end %}
{% end %}
</div>
{% end %}
</body></html>
"""


def _env(templates: dict[str, str]) -> Environment:
    from chirp.templating.suspense import DEFERRED

    env = Environment(loader=DictLoader(templates))
    env.add_test("deferred", lambda val: val is DEFERRED)
    return env


def _attempt_mutation(value: object, attribute: str, replacement: object) -> None:
    setattr(value, attribute, replacement)


@pytest.mark.issue(948)
def test_independent_defers_form_dag_without_couples() -> None:
    env = _env({"dashboard.html": _INDEPENDENT_TEMPLATE})
    plan = plan_defer_execution(env, "dashboard.html", {"stats", "feed"})

    assert plan.deferred_keys == ("feed", "stats")
    assert set(plan.blocks) == {"feed", "stats"}
    assert plan.pruned_ancestors == ()
    assert plan.independent_keys() == frozenset({"stats", "feed"})
    assert plan.coupled_key_pairs() == frozenset()
    assert {("feeds", e.source, e.destination) for e in plan.edges if e.kind == "feeds"} == {
        ("feeds", "stats", "stats"),
        ("feeds", "feed", "feed"),
    }
    assert not any(e.kind == "couples" for e in plan.edges)


@pytest.mark.issue(948)
def test_coupled_defers_retain_shared_block_edges() -> None:
    env = _env({"coupled.html": _COUPLED_TEMPLATE})
    plan = plan_defer_execution(env, "coupled.html", {"stats", "feed"})

    assert plan.blocks == ("panel",)
    assert plan.independent_keys() == frozenset()
    assert plan.coupled_key_pairs() == frozenset({("feed", "stats")})
    assert DeferEdge("feeds", "feed", "panel") in plan.edges
    assert DeferEdge("feeds", "stats", "panel") in plan.edges
    assert DeferEdge("couples", "feed", "stats") in plan.edges


@pytest.mark.issue(948)
def test_ancestor_superset_pruning_still_holds() -> None:
    env = _env({"shared_key.html": _ANCESTOR_TEMPLATE})
    plan = plan_defer_execution(env, "shared_key.html", {"stars"})

    assert "page_content" in plan.pruned_ancestors
    assert "page_content" not in plan.blocks
    assert set(plan.blocks) == {"hero_stars", "footer_stars"}
    assert plan.independent_keys() == frozenset({"stars"})
    assert all(edge.destination != "page_content" for edge in plan.edges if edge.kind == "feeds")


@pytest.mark.issue(948)
def test_dashboard_route_compiles_explicit_defer_dag(tmp_path) -> None:
    (tmp_path / "dashboard.html").write_text(_INDEPENDENT_TEMPLATE, encoding="utf-8")
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))

    async def _stats() -> str:
        await asyncio.sleep(0)
        return "42"

    async def _feed() -> str:
        await asyncio.sleep(0)
        return "hello"

    @app.route("/")
    async def dashboard():
        return Suspense("dashboard.html", stats=_stats(), feed=_feed())

    app.freeze()
    dag = app._runtime_state._suspense_defer_dag
    assert dag is not None
    route_plan = dag.plan_for_route(path="/", method="GET")
    assert route_plan is not None
    assert route_plan.template_name == "dashboard.html"
    assert route_plan.independent_keys() == frozenset({"stats", "feed"})
    assert route_plan.coupled_key_pairs() == frozenset()
    assert set(route_plan.plan.blocks) == {"stats", "feed"}
    assert {node.key for node in dag.keys} == {"stats", "feed"}
    assert {node.name for node in dag.blocks} == {"stats", "feed"}
    assert any(edge.kind == "feeds" for edge in dag.edges)
    assert not any(edge.kind == "couples" for edge in dag.edges)


@pytest.mark.issue(948)
async def test_suspense_route_resolves_independent_leaves_concurrently(tmp_path) -> None:
    (tmp_path / "dashboard.html").write_text(_INDEPENDENT_TEMPLATE, encoding="utf-8")
    app = App(AppConfig(template_dir=tmp_path, skip_contract_checks=True))
    started = asyncio.Event()
    release = asyncio.Event()
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def _gate(label: str) -> str:
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            if in_flight >= 2:
                started.set()
        await release.wait()
        async with lock:
            in_flight -= 1
        return label

    @app.route("/")
    async def dashboard():
        return Suspense(
            "dashboard.html",
            stats=_gate("STATS"),
            feed=_gate("FEED"),
        )

    app.freeze()
    dag = app._runtime_state._suspense_defer_dag
    assert dag is not None
    assert dag.plan_for_template("dashboard.html") is not None
    assert dag.plan_for_template("dashboard.html").independent_keys() == frozenset(
        {"stats", "feed"}
    )

    async with TestClient(app) as client:
        request_task = asyncio.create_task(client.get("/"))
        await asyncio.wait_for(started.wait(), timeout=2.0)
        assert max_in_flight >= 2
        release.set()
        response = await request_task

    assert response.status == 200
    body = response.text
    # Shell retains skeleton markup; deferred OOB chunks carry the loaded values
    # (browser / htmx swaps replace the skeletons). Concurrent proof is the
    # in-flight gate above plus both loaded markers in the streamed body.
    assert "LOADED-STATS:STATS" in body
    assert "LOADED-FEED:FEED" in body
    assert max_in_flight >= 2


@pytest.mark.issue(948)
def test_compiled_dag_is_immutable_with_stable_digest(tmp_path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        (directory / "dashboard.html").write_text(_INDEPENDENT_TEMPLATE, encoding="utf-8")

    def _build(path) -> App:
        app = App(AppConfig(template_dir=path, skip_contract_checks=True))

        @app.route("/")
        async def dashboard():
            async def _stats() -> str:
                return "1"

            async def _feed() -> str:
                return "2"

            return Suspense("dashboard.html", stats=_stats(), feed=_feed())

        app.freeze()
        return app

    left = _build(first)
    right = _build(second)
    left_dag = left._runtime_state._suspense_defer_dag
    right_dag = right._runtime_state._suspense_defer_dag
    assert left_dag is not None
    assert right_dag is not None
    assert left_dag.topology_digest == right_dag.topology_digest
    with pytest.raises(FrozenInstanceError):
        _attempt_mutation(left_dag, "edges", ())
    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = tuple(pool.map(lambda _: left_dag.topology_digest, range(32)))
    assert set(digests) == {left_dag.topology_digest}


@pytest.mark.issue(948)
def test_duplicate_dag_identity_fails_loud() -> None:
    from chirp.app._suspense_dag import _SuspenseRoutePlan

    plan = DeferExecutionPlan(
        template_name="x.html",
        deferred_keys=("a",),
        blocks=("a",),
        key_to_blocks=(("a", ("a",)),),
        pruned_ancestors=(),
        edges=(),
    )
    node = _SuspenseRoutePlan(
        id=stable_identity("suspense_plan", "GET", "/", "x.html", "0"),
        route_id=stable_identity("route", "GET", "/"),
        path="/",
        method="GET",
        template_name="x.html",
        plan=plan,
        origin=SourceOrigin("handler", "test"),
    )
    with pytest.raises(ConfigurationError, match="Duplicate suspense defer DAG"):
        _SuspenseDeferDAG(routes=(node, node))
