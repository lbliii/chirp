"""Compiled-transition correlation and coverage proof for issue #511."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chirp import OOB, App, AppConfig, EventStream, Fragment, Page, Suspense
from chirp.testing import TestClient, transition_coverage, transition_observation

pytestmark = pytest.mark.issue(511)


def _write_template(path: Path) -> None:
    path.joinpath("page.html").write_text(
        "{% block page_root %}<!doctype html><html><body>"
        "<main id='main'>{% block content %}{{ message }}{% end %}</main>"
        "{% block toast %}<aside id='toast'>{{ toast | default('') }}</aside>{% end %}"
        "</body></html>{% end %}",
        encoding="utf-8",
    )


def _build_app(tmp_path: Path) -> App:
    _write_template(tmp_path)
    app = App(AppConfig(debug=True, skip_contract_checks=True, template_dir=tmp_path))
    app._mutable_state.page_templates.add("page.html")
    app._mutable_state.page_leaf_templates.add("page.html")
    app.register_fragment_target("main", fragment_block="page_root")
    app.register_fragment_target(
        "content",
        fragment_block="content",
        triggers_shell_update=False,
    )

    @app.route("/page", template="page.html")
    def page() -> Page:
        return Page("page.html", "content", page_block_name="page_root", message="hello")

    @app.route("/items/{item_id}", template="page.html")
    def item(item_id: str) -> Page:
        return Page("page.html", "content", page_block_name="page_root", message=item_id)

    @app.route("/save", methods=["POST"], template="page.html")
    def save() -> OOB:
        return OOB(
            Fragment("page.html", "content", message="saved"),
            Fragment("page.html", "toast", toast="done"),
        )

    @app.route("/suspense", template="page.html")
    def suspense() -> Suspense:
        return Suspense("page.html", message="ready")

    @app.route("/events")
    def events() -> EventStream:
        async def generate():
            yield "hello"

        return EventStream(generate())

    return app


async def test_same_route_has_distinct_normal_boosted_and_targeted_observations(
    tmp_path: Path,
) -> None:
    app = _build_app(tmp_path)

    async with TestClient(app) as client:
        normal = await client.get("/page")
        boosted = await client.boosted("/page", target="main")
        targeted = await client.fragment("/page", target="content")

    observations = [transition_observation(response) for response in (normal, boosted, targeted)]
    assert {item.request_mode for item in observations} == {"normal", "boosted", "targeted"}
    assert len({item.observation_id for item in observations}) == 3
    assert len({item.route_id for item in observations}) == 1
    assert all(item.route_path == "/page" for item in observations)
    assert any(
        "route_template" in line for item in observations for line in item.transition_descriptions
    )
    assert any(
        "target_block" in line for item in observations for line in item.transition_descriptions
    )


async def test_mutation_oob_suspense_and_sse_modes_are_recorded(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async with TestClient(app) as client:
        mutation = await client.fragment("/save", method="POST", target="content")
        suspense = await client.get("/suspense")
        sse = await client.sse("/events", max_events=1)

    mutation_evidence = transition_observation(mutation)
    suspense_evidence = transition_observation(suspense)
    sse_evidence = transition_observation(sse)
    assert {"targeted", "mutation", "oob"} <= set(mutation_evidence.mode_tags)
    assert {"normal", "suspense"} <= set(suspense_evidence.mode_tags)
    assert {"normal", "sse"} <= set(sse_evidence.mode_tags)


async def test_transition_coverage_reports_intentionally_untested_mode(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async with TestClient(app) as client:
        normal = await client.get("/page")
        targeted = await client.fragment("/page", target="content")

    targeted_observation = transition_observation(targeted)
    expected_transition = targeted_observation.compiled_transition_ids[0]
    report = transition_coverage(
        [normal, targeted],
        expected_modes=("normal", "boosted", "targeted"),
        expected_transition_ids=(expected_transition, "transition:not-observed"),
    )
    assert report.observed_modes == ("normal", "targeted")
    assert report.untested_modes == ("boosted",)
    assert report.unexercised_transition_ids == ("transition:not-observed",)
    assert not report.complete
    assert "Untested request modes: boosted" in report.summary()


async def test_debug_trace_export_uses_route_pattern_and_bounded_records(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async with TestClient(app) as client:
        await client.get("/page")
        response = await client.get("/__chirp/debug/traces.json")

    payload = json.loads(response.text)
    http_records = [record for record in payload["records"] if record["channel"] == "http"]
    assert http_records
    record = http_records[-1]
    assert record["path"] == "/page"
    assert record["data"]["observation_id"].startswith("observation:")
    assert record["data"]["transition_descriptions"]
    assert len(payload["records"]) <= 500


async def test_trace_redacts_dynamic_path_values_and_context_values(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    private_value = "sensitive-route-value-42"

    async with TestClient(app) as client:
        response = await client.get(f"/items/{private_value}")
        traces = await client.get("/__chirp/debug/traces.json")

    observation = transition_observation(response)
    assert observation.route_path == "/items/{item_id}"
    assert private_value not in json.dumps(json.loads(traces.text))


def test_transition_coverage_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match=r"Unknown transition mode.*browser-magic"):
        transition_coverage([], expected_modes=("browser-magic",))


async def test_compiler_trace_metadata_remains_debug_only(tmp_path: Path) -> None:
    _write_template(tmp_path)
    app = App(AppConfig(debug=False, skip_contract_checks=True, template_dir=tmp_path))

    @app.route("/", template="page.html")
    def index() -> Page:
        return Page("page.html", "content", page_block_name="page_root", message="hello")

    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.header("X-Chirp-Return-Trace") is None
    assert app._runtime_state.debug_wiring.trace_store is None
