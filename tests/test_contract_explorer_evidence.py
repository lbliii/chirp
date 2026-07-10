"""Regression proof for the private Contract Explorer evidence overlay."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.contracts.explorer_evidence import overlay_explorer_evidence
from chirp.contracts.explorer_projection import ExplorerProjection, build_explorer_projection
from chirp.contracts.types import CheckResult
from chirp.server.debug_runtime import DebugTraceStore, build_runtime_debug_wiring
from chirp.server.intent_timeline import _http_drafts, _IntentCapture
from chirp.templating.trace import ReturnTrace


def _topology(tmp_path: Path) -> tuple[ExplorerProjection, str, str]:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "page.html").write_text(
        "{% block page_root %}{% block content %}ok{% endblock %}{% endblock %}",
        encoding="utf-8",
    )
    app = App(
        AppConfig(
            template_dir=tmp_path,
            debug=False,
            skip_contract_checks=True,
        )
    )

    @app.route("/", name="home", template="page.html")
    def home() -> str:
        return "not executed"

    app._mutable_state.page_templates.add("page.html")
    app._mutable_state.page_leaf_templates.add("page.html")
    app.freeze()
    program = app._runtime_state.hypermedia_program
    assert program is not None
    topology = build_explorer_projection(program, CheckResult())
    route = next(node for node in topology.nodes if node.kind == "route")
    transition = next(edge for edge in topology.edges if edge.source_id == route.id)
    return topology, route.id, transition.id


def _trace(
    route_id: str | None,
    transition_ids: tuple[str, ...],
    *,
    observation_id: str | None = "observation:home:page",
) -> ReturnTrace:
    return ReturnTrace(
        return_type="Page",
        category="composition",
        is_htmx=False,
        method="GET",
        render_intent="page",
        status=200,
        template="page.html",
        route_id=route_id,
        observation_id=observation_id,
        request_mode="page",
        compiled_transition_ids=transition_ids,
    )


def _record(store: DebugTraceStore, trace: ReturnTrace, index: int) -> None:
    store.record_http(
        trace=trace,
        request_id=f"request-{index}",
        internal=False,
        owner="app",
    )


@pytest.mark.issue(655)
def test_runtime_evidence_stays_separate_from_static_contract_truth(tmp_path: Path) -> None:
    topology, route_id, transition_id = _topology(tmp_path)
    store = DebugTraceStore()
    trace = _trace(route_id, (transition_id, transition_id))
    _record(store, trace, 1)
    _record(store, trace, 2)

    overlay = overlay_explorer_evidence(topology, store.snapshot())

    assert overlay.topology is topology
    assert overlay.capture.state == "active"
    assert overlay.capture.response_observation_count == 2
    assert [item.state for item in overlay.observations] == ["matched", "matched"]
    assert overlay.unmatched_observations == ()
    assert len(overlay.transitions) == 1
    transition = overlay.transitions[0]
    assert transition.transition_id == transition_id
    assert transition.count == 2
    assert transition.first_observed_sequence == 3
    assert transition.last_observed_sequence == 6
    assert transition.last_route_id == route_id
    assert transition.last_request_mode == "page"
    assert topology.edges
    assert topology.findings == ()
    with pytest.raises(FrozenInstanceError):
        transition.count = 3  # type: ignore[misc]  # intentional frozen-write probe


@pytest.mark.issue(655)
def test_overlay_preserves_capture_order_and_explicit_truncation(tmp_path: Path) -> None:
    topology, route_id, transition_id = _topology(tmp_path)
    store = DebugTraceStore(limit=4)
    trace = _trace(route_id, (transition_id,))
    for index in range(3):
        _record(store, trace, index)

    overlay = overlay_explorer_evidence(topology, store.snapshot())

    assert [item.sequence for item in overlay.observations] == [6, 9]
    assert overlay.capture.retained_observation_count == 4
    assert overlay.capture.response_observation_count == 2
    assert overlay.capture.truncated
    assert overlay.capture.dropped_count == 5
    assert overlay.capture.first_retained_sequence == 6
    assert overlay.transitions[0].count == 2


@pytest.mark.issue(655)
def test_overlay_reports_capture_lifecycle_without_cross_lifecycle_counts(
    tmp_path: Path,
) -> None:
    topology, route_id, transition_id = _topology(tmp_path)
    trace = _trace(route_id, (transition_id,))
    first = _IntentCapture()
    first.publish_many(_http_drafts(trace, request_id="first", internal=False, owner="app"))
    first_overlay = overlay_explorer_evidence(topology, first.close())

    second = _IntentCapture()
    second.publish_many(_http_drafts(trace, request_id="second", internal=False, owner="app"))
    second_overlay = overlay_explorer_evidence(topology, second.snapshot())

    assert first_overlay.capture.state == "closed"
    assert second_overlay.capture.state == "active"
    assert first_overlay.observations[0].sequence == 3
    assert second_overlay.observations[0].sequence == 3
    assert first_overlay.transitions[0].count == 1
    assert second_overlay.transitions[0].count == 1


@pytest.mark.issue(655)
def test_concurrent_observers_publish_one_ordered_bounded_overlay(tmp_path: Path) -> None:
    topology, route_id, transition_id = _topology(tmp_path)
    trace = _trace(route_id, (transition_id,))
    store = DebugTraceStore(limit=300)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: _record(store, trace, index), range(64)))

    overlay = overlay_explorer_evidence(topology, store.snapshot())
    sequences = [item.sequence for item in overlay.observations]
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences)) == 64
    assert overlay.transitions[0].count == 64
    assert overlay.transitions[0].last_observed_sequence == sequences[-1]


@pytest.mark.issue(655)
def test_stale_and_identity_free_evidence_remain_explicit(tmp_path: Path) -> None:
    topology, _route_id, transition_id = _topology(tmp_path)
    store = DebugTraceStore()
    _record(
        store,
        _trace("route:removed", (transition_id, "transition:removed")),
        1,
    )
    _record(store, _trace(None, (), observation_id=None), 2)

    overlay = overlay_explorer_evidence(topology, store.snapshot())

    assert [item.state for item in overlay.observations] == ["stale", "unknown"]
    assert overlay.unmatched_observations == overlay.observations
    assert overlay.observations[0].route_id == "route:removed"
    assert overlay.observations[0].matched_transition_ids == (transition_id,)
    assert overlay.observations[0].unmatched_transition_ids == ("transition:removed",)
    assert overlay.observations[1].matched_transition_ids == ()
    assert overlay.transitions[0].count == 1


@pytest.mark.issue(655)
def test_production_has_no_capture_and_internal_debug_traffic_is_excluded(
    tmp_path: Path,
) -> None:
    topology, route_id, transition_id = _topology(tmp_path)
    production_wiring = build_runtime_debug_wiring(AppConfig(debug=False))
    assert production_wiring.trace_store is None

    unavailable = overlay_explorer_evidence(topology, production_wiring.trace_store)
    assert unavailable.capture.state == "unavailable"
    assert unavailable.observations == ()
    assert unavailable.topology is topology

    store = DebugTraceStore()
    store.record_http(
        trace=_trace(route_id, (transition_id,)),
        request_id="internal",
        internal=True,
        owner="devtools",
    )
    internal = overlay_explorer_evidence(topology, store.snapshot(include_internal=True))
    assert internal.capture.retained_observation_count == 3
    assert internal.capture.response_observation_count == 0
    assert internal.observations == ()
