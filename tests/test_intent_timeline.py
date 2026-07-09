"""Regression proof for private Intent Timeline capture (#647)."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from chirp import App, AppConfig
from chirp.server.debug_runtime import (
    DEBUG_TRACES_PATH,
    DebugTraceStore,
    build_runtime_debug_wiring,
)
from chirp.server.intent_timeline import (
    _diagnostic_draft,
    _IntentCapture,
    _observation_mapping,
    _ResponseObservation,
    _SSEObservation,
)
from chirp.templating.trace import ReturnTrace
from chirp.testing import TestClient


def _return_trace(secret: str = "") -> ReturnTrace:
    return ReturnTrace(
        return_type="Fragment",
        category="composition",
        is_htmx=True,
        method="POST",
        request_content_type=f"multipart/form-data; boundary={secret}",
        render_intent="fragment",
        status=200,
        template="page.html",
        block="content",
        target="content",
        swap="innerHTML",
        context_keys=(f"private-context-{secret}",),
        notes=(f"private-note-{secret}",),
        route_id="route:items",
        route_path="/items/{item_id}",
        observation_id="observation:items:targeted",
        request_mode="targeted",
        mode_tags=("targeted",),
        compiled_transition_ids=("transition:items:content",),
        transition_descriptions=("target_block: content",),
    )


@pytest.mark.issue(647)
def test_http_observations_are_immutable_ordered_and_causally_linked() -> None:
    store = DebugTraceStore()

    response_sequence = store.record_http(
        trace=_return_trace(),
        request_id="request-1",
        internal=False,
        owner="app",
    )

    snapshot = store.snapshot()
    assert [item.sequence for item in snapshot.observations] == [1, 2, 3]
    assert [item.phase for item in snapshot.observations] == [
        "request",
        "render-intent",
        "response",
    ]
    assert [item.parent_sequence for item in snapshot.observations] == [None, 1, 2]
    assert response_sequence == 3
    observation = snapshot.observations[-1]
    assert isinstance(observation.detail, _ResponseObservation)
    response_data = _observation_mapping(observation)["data"]
    assert response_data["return_type"] == "Fragment"
    assert response_data["render_intent"] == "fragment"
    assert response_data["request_content_type"] == "multipart/form-data"
    assert response_data["route_path"] == "/items/{item_id}"
    assert response_data["observation_id"] == "observation:items:targeted"
    assert response_data["compiled_transition_ids"] == ("transition:items:content",)
    with pytest.raises(FrozenInstanceError):
        observation.phase = "changed"  # type: ignore[misc]  # intentional frozen-write probe
    with pytest.raises(FrozenInstanceError):
        observation.detail.status = 500  # type: ignore[misc]  # intentional frozen-write probe


@pytest.mark.issue(647)
def test_capture_marks_record_and_byte_truncation_deterministically() -> None:
    store = DebugTraceStore(limit=3)
    for index in range(5):
        store.record_diagnostic(f"diagnostic-{index}")

    snapshot = store.snapshot()
    assert [item.sequence for item in snapshot.observations] == [3, 4, 5]
    assert snapshot.truncation is not None
    assert snapshot.truncation.dropped_count == 2
    assert snapshot.truncation.first_retained_sequence == 3

    byte_bounded = DebugTraceStore(limit=10, byte_limit=1)
    byte_bounded.record_diagnostic("too-large")
    byte_snapshot = byte_bounded.snapshot()
    assert byte_snapshot.observations == ()
    assert byte_snapshot.retained_bytes == 0
    assert byte_snapshot.truncation is not None
    assert byte_snapshot.truncation.dropped_count == 1
    assert byte_snapshot.truncation.first_retained_sequence is None


@pytest.mark.issue(647)
def test_capture_lifecycles_are_isolated_and_cannot_be_reopened() -> None:
    first = _IntentCapture()
    first.publish(_diagnostic_draft("first"))
    closed = first.close()

    assert not closed.active
    assert [item.sequence for item in closed.observations] == [1]
    with pytest.raises(RuntimeError, match="capture is closed"):
        first.publish(_diagnostic_draft("after-close"))

    second = _IntentCapture()
    observation = second.publish(_diagnostic_draft("second"))
    assert observation.sequence == 1
    assert second.snapshot().active


@pytest.mark.issue(647)
def test_concurrent_writers_publish_one_total_order() -> None:
    store = DebugTraceStore(limit=1_000)

    with ThreadPoolExecutor(max_workers=16) as executor:
        tuple(executor.map(store.record_diagnostic, (f"writer-{index}" for index in range(500))))

    observations = store.snapshot().observations
    assert len(observations) == 500
    assert [item.sequence for item in observations] == list(range(1, 501))
    assert len({item.sequence for item in observations}) == 500


@pytest.mark.issue(647)
def test_capture_never_retains_bodies_headers_cookies_or_context() -> None:
    secret = "sensitive-value-42"
    store = DebugTraceStore()
    parent_sequence = store.record_http(
        trace=_return_trace(secret),
        request_id="request-1",
        internal=False,
        owner="app",
    )
    store.record_sse(
        phase="generator_error",
        path="/items/{item_id}",
        request_id="request-1",
        parent_sequence=parent_sequence,
        internal=False,
        owner="app",
        data={
            "authorization": f"Bearer {secret}",
            "body": secret,
            "cookie": f"session={secret}",
            "context": {"user": secret},
            "event": secret,
            "id": secret,
            "message": secret,
            "error_type": "ValueError",
        },
    )

    retained = json.dumps(store.snapshot(), default=str)
    assert secret not in retained
    sse = store.snapshot().observations[-1]
    assert isinstance(sse.detail, _SSEObservation)
    assert sse.parent_sequence == parent_sequence
    assert sse.detail.error_type == "ValueError"


@pytest.mark.issue(647)
async def test_debug_trace_uses_opaque_correlation_for_request_id_header() -> None:
    secret_request_id = "private-caller-request-id-42"
    app = App(AppConfig(debug=True))

    @app.route("/")
    def index():
        return "ok"

    async with TestClient(app) as client:
        await client.get("/", headers={"X-Request-ID": secret_request_id})
        traces = await client.get(DEBUG_TRACES_PATH)

    payload = json.loads(traces.text)
    records = [record for record in payload["records"] if record["path"] == "/"]
    assert [record["phase"] for record in records] == [
        "request",
        "render-intent",
        "response",
    ]
    correlation_ids = {record["request_id"] for record in records}
    assert len(correlation_ids) == 1
    assert next(iter(correlation_ids)).startswith("capture:")
    assert secret_request_id not in traces.text


@pytest.mark.issue(647)
def test_production_default_allocates_no_capture_store() -> None:
    app = App(AppConfig(debug=False))
    app._ensure_frozen()
    assert app._runtime_state.debug_wiring.trace_store is None
    assert build_runtime_debug_wiring(AppConfig(debug=False)).trace_store is None
