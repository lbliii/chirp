"""``defer_coupling`` contract rule (#949).

Uses the freeze-time Suspense defer DAG to warn when deferred keys share a
leaf block (``couples`` edges). Severity is env-aware: silent in development,
WARNING in staging/production.
"""

from __future__ import annotations

import asyncio

import pytest

from chirp import App, AppConfig, Suspense
from chirp.app._suspense_dag import _SuspenseDeferDAG, _SuspenseRoutePlan
from chirp.app.hypermedia_program import SourceOrigin, stable_identity
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.rules_defer_coupling import check_defer_coupling
from chirp.contracts.types import Severity
from chirp.templating.suspense import DeferEdge, DeferExecutionPlan

_INDEPENDENT = """\
<html><body>
<div id="stats">
{% block stats %}
  {% if stats is deferred %}<span>…</span>{% else %}<span>{{ stats }}</span>{% end %}
{% end %}
</div>
<div id="feed">
{% block feed %}
  {% if feed is deferred %}<span>…</span>{% else %}<span>{{ feed }}</span>{% end %}
{% end %}
</div>
</body></html>
"""

_COUPLED = """\
<html><body>
{% block panel %}
  {% if stats is deferred %}
    <span>…</span>
  {% elif feed is deferred %}
    <span>…</span>
  {% else %}
    <span>{{ stats }}|{{ feed }}</span>
  {% end %}
{% end %}
</body></html>
"""


def _coupled_dag() -> _SuspenseDeferDAG:
    plan = DeferExecutionPlan(
        template_name="coupled.html",
        deferred_keys=("feed", "stats"),
        blocks=("panel",),
        key_to_blocks=(("feed", ("panel",)), ("stats", ("panel",))),
        pruned_ancestors=(),
        edges=(
            DeferEdge("feeds", "feed", "panel"),
            DeferEdge("feeds", "stats", "panel"),
            DeferEdge("couples", "feed", "stats"),
        ),
    )
    route = _SuspenseRoutePlan(
        id=stable_identity("suspense_plan", "GET", "/", "coupled.html", "0"),
        route_id=stable_identity("route", "GET", "/"),
        path="/",
        method="GET",
        template_name="coupled.html",
        plan=plan,
        origin=SourceOrigin("handler", "test"),
    )
    return _SuspenseDeferDAG(routes=(route,))


def _independent_dag() -> _SuspenseDeferDAG:
    plan = DeferExecutionPlan(
        template_name="dashboard.html",
        deferred_keys=("feed", "stats"),
        blocks=("feed", "stats"),
        key_to_blocks=(("feed", ("feed",)), ("stats", ("stats",))),
        pruned_ancestors=(),
        edges=(
            DeferEdge("feeds", "feed", "feed"),
            DeferEdge("feeds", "stats", "stats"),
        ),
    )
    route = _SuspenseRoutePlan(
        id=stable_identity("suspense_plan", "GET", "/", "dashboard.html", "0"),
        route_id=stable_identity("route", "GET", "/"),
        path="/",
        method="GET",
        template_name="dashboard.html",
        plan=plan,
        origin=SourceOrigin("handler", "test"),
    )
    return _SuspenseDeferDAG(routes=(route,))


@pytest.mark.issue(949)
def test_unit_coupled_pair_warns_outside_development() -> None:
    """Direct rule call: couples edges → WARNING in staging/production."""
    dag = _coupled_dag()

    assert check_defer_coupling(dag, env="development") == []

    staging = check_defer_coupling(dag, env="staging")
    assert len(staging) == 1
    assert staging[0].severity is Severity.WARNING
    assert staging[0].category == "defer_coupling"
    assert staging[0].template == "coupled.html"
    assert staging[0].route == "/"
    assert "stats" in staging[0].message
    assert "feed" in staging[0].message
    assert "panel" in staging[0].message

    production = check_defer_coupling(dag, env="production")
    assert len(production) == 1
    assert production[0].severity is Severity.WARNING


@pytest.mark.issue(949)
def test_unit_independent_keys_are_silent() -> None:
    dag = _independent_dag()
    for env in ("development", "staging", "production"):
        assert check_defer_coupling(dag, env=env) == []


@pytest.mark.issue(949)
def test_unit_none_dag_is_silent() -> None:
    assert check_defer_coupling(None, env="production") == []


def _suspense_app(tmp_path, template_html: str, *, env: str = "development") -> App:
    (tmp_path / "page.html").write_text(template_html, encoding="utf-8")
    kwargs = {"secret_key": "x" * 32} if env in ("staging", "production") else {}
    app = App(
        AppConfig(
            template_dir=str(tmp_path),
            skip_contract_checks=True,
            env=env,
            **kwargs,
        )
    )

    async def _stats() -> str:
        await asyncio.sleep(0)
        return "42"

    async def _feed() -> str:
        await asyncio.sleep(0)
        return "hello"

    @app.route("/")
    async def dashboard():
        return Suspense("page.html", stats=_stats(), feed=_feed())

    return app


@pytest.mark.issue(949)
def test_app_check_flags_coupled_keys_in_staging(tmp_path) -> None:
    app = _suspense_app(tmp_path, _COUPLED, env="staging")
    app.freeze()
    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "defer_coupling"]
    assert len(issues) == 1
    assert issues[0].severity is Severity.WARNING
    assert "panel" in issues[0].message
    assert issues[0].template == "page.html"


@pytest.mark.issue(949)
def test_app_check_silent_for_coupled_keys_in_development(tmp_path) -> None:
    app = _suspense_app(tmp_path, _COUPLED, env="development")
    app.freeze()
    result = check_hypermedia_surface(app)
    assert [i for i in result.issues if i.category == "defer_coupling"] == []


@pytest.mark.issue(949)
def test_app_check_silent_for_independent_keys_in_production(tmp_path) -> None:
    app = _suspense_app(tmp_path, _INDEPENDENT, env="production")
    app.freeze()
    result = check_hypermedia_surface(app)
    assert [i for i in result.issues if i.category == "defer_coupling"] == []
    dag = app._runtime_state._suspense_defer_dag
    assert dag is not None
    plan = dag.plan_for_route(path="/", method="GET")
    assert plan is not None
    assert plan.independent_keys() == frozenset({"stats", "feed"})


@pytest.mark.issue(949)
def test_override_promotes_coupling_to_error(tmp_path) -> None:
    app = _suspense_app(tmp_path, _COUPLED, env="staging")
    app.override_contract_severity("defer_coupling", Severity.ERROR)
    app.freeze()
    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "defer_coupling"]
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR


@pytest.mark.issue(949)
def test_explicit_defer_blocks_couples_all_listed_keys(tmp_path) -> None:
    """defer_blocks= feeds every key into every listed block → couples edges."""
    template = """\
<html><body>
{% block panel %}
  {% if stats is deferred or feed is deferred %}<span>…</span>
  {% else %}<span>{{ stats }}|{{ feed }}</span>{% end %}
{% end %}
</body></html>
"""
    (tmp_path / "page.html").write_text(template, encoding="utf-8")
    app = App(
        AppConfig(
            template_dir=str(tmp_path),
            skip_contract_checks=True,
            env="production",
            secret_key="x" * 32,
        )
    )

    async def _stats() -> str:
        return "s"

    async def _feed() -> str:
        return "f"

    @app.route("/")
    async def dashboard():
        return Suspense(
            "page.html",
            defer_blocks=("panel",),
            stats=_stats(),
            feed=_feed(),
        )

    app.freeze()
    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "defer_coupling"]
    assert len(issues) == 1
    assert "defer_blocks" in issues[0].message
