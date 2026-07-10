"""Private replay artifact and semantic comparator proof (#648)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chirp.server.intent_replay import (
    _MAX_ARTIFACT_BYTES,
    _compare_replay_artifacts,
    _dump_replay_artifact,
    _load_replay_artifact,
    _parse_replay_artifact,
    _ReplayArtifactError,
)
from chirp.server.intent_timeline import (
    _CaptureSnapshot,
    _DiagnosticObservation,
    _IntentObservation,
    _RenderIntentObservation,
    _RequestObservation,
    _ResponseObservation,
    _SSEObservation,
)

pytestmark = pytest.mark.issue(648)

_FINGERPRINT = "sha256:" + "a" * 64
_REQUEST_ID = "capture:" + "1" * 32


def _observations() -> tuple[_IntentObservation, ...]:
    return (
        _IntentObservation(
            sequence=1,
            elapsed_us=10,
            ts_ms=1_750_000_000_000,
            channel="http",
            phase="request",
            route_pattern="/items/{item_id}",
            request_id=_REQUEST_ID,
            parent_sequence=None,
            internal=False,
            owner="app",
            detail=_RequestObservation(
                method="POST",
                route_id="route:items",
                request_mode="targeted",
                mode_tags=("targeted",),
            ),
        ),
        _IntentObservation(
            sequence=2,
            elapsed_us=20,
            ts_ms=1_750_000_000_001,
            channel="http",
            phase="render-intent",
            route_pattern="/items/{item_id}",
            request_id=_REQUEST_ID,
            parent_sequence=1,
            internal=False,
            owner="app",
            detail=_RenderIntentObservation(
                return_type="Fragment",
                category="composition",
                render_intent="fragment",
                template="items/page.html",
                block="content",
                target="content",
                swap="innerHTML",
                streaming=False,
                sse=False,
            ),
        ),
        _IntentObservation(
            sequence=3,
            elapsed_us=30,
            ts_ms=1_750_000_000_002,
            channel="http",
            phase="response",
            route_pattern="/items/{item_id}",
            request_id=_REQUEST_ID,
            parent_sequence=2,
            internal=False,
            owner="app",
            detail=_ResponseObservation(
                return_type="Fragment",
                category="composition",
                is_htmx=True,
                method="POST",
                request_content_type="application/x-www-form-urlencoded",
                render_intent="fragment",
                status=200,
                template="items/page.html",
                block="content",
                target="content",
                swap="innerHTML",
                streaming=False,
                sse=False,
                observation_id="observation:items:targeted",
                route_id="route:items",
                route_path="/items/{item_id}",
                request_mode="targeted",
                mode_tags=("targeted",),
                compiled_transition_ids=("transition:items:content",),
                transition_descriptions=("target_block: content",),
            ),
        ),
        _IntentObservation(
            sequence=4,
            elapsed_us=40,
            ts_ms=1_750_000_000_003,
            channel="sse",
            phase="event",
            route_pattern="/items/{item_id}/live",
            request_id=_REQUEST_ID,
            parent_sequence=3,
            internal=False,
            owner="app",
            detail=_SSEObservation(
                dialect="htmx4",
                heartbeat_interval=15.0,
                retry_ms=1_000,
                retry=1_000,
                data_lines=1,
                message_class="fragment",
                value_type="str",
                target="price",
                swap="innerHTML",
                during="open",
                error_type=None,
            ),
        ),
        _IntentObservation(
            sequence=5,
            elapsed_us=50,
            ts_ms=1_750_000_000_004,
            channel="diagnostic",
            phase="diagnostic",
            route_pattern=None,
            request_id=None,
            parent_sequence=None,
            internal=False,
            owner="chirp",
            detail=_DiagnosticObservation(code="capture-complete"),
        ),
    )


def _snapshot() -> _CaptureSnapshot:
    return _CaptureSnapshot(
        observations=_observations(),
        active=False,
        retained_bytes=2_048,
        truncation=None,
    )


def _artifact_bytes() -> bytes:
    return _dump_replay_artifact(
        _snapshot(),
        chirp_version="0.10.1",
        program_fingerprint=_FINGERPRINT,
    )


def _payload() -> dict[str, object]:
    return json.loads(_artifact_bytes())


def _parse_payload(payload: dict[str, object], *, name: str = "fixture.chirp-replay"):
    return _parse_replay_artifact(
        json.dumps(payload, separators=(",", ":")).encode(),
        source_name=name,
    )


def test_round_trip_preserves_every_supported_observation_variant(tmp_path: Path) -> None:
    path = tmp_path / "timeline.chirp-replay"
    encoded = _artifact_bytes()
    path.write_bytes(encoded)

    artifact = _load_replay_artifact(path)

    assert artifact.chirp_version == "0.10.1"
    assert artifact.program_fingerprint == _FINGERPRINT
    assert artifact.source == "debug-test"
    assert not artifact.truncated
    assert [type(item.detail) for item in artifact.observations] == [
        _RequestObservation,
        _RenderIntentObservation,
        _ResponseObservation,
        _SSEObservation,
        _DiagnosticObservation,
    ]
    for expected, loaded in zip(_observations(), artifact.observations, strict=True):
        assert loaded.sequence == expected.sequence
        assert loaded.elapsed_us == expected.elapsed_us
        assert loaded.channel == expected.channel
        assert loaded.phase == expected.phase
        assert loaded.route_pattern == expected.route_pattern
        assert loaded.request_id == expected.request_id
        assert loaded.parent_sequence == expected.parent_sequence
        assert loaded.detail == expected.detail
        assert loaded.ts_ms == 0

    text = encoded.decode()
    assert '"ts_ms"' not in text
    for forbidden in ("body", "html", "cookies", "session", "authorization", "context"):
        assert f'"{forbidden}"' not in text


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not-json", "invalid JSON"),
        (b"\xff", "not valid UTF-8"),
    ],
)
def test_corrupt_artifacts_fail_loud(data: bytes, message: str) -> None:
    with pytest.raises(_ReplayArtifactError, match=message):
        _parse_replay_artifact(data, source_name="corrupt.chirp-replay")


def test_oversized_artifact_fails_before_json_parsing() -> None:
    data = b"x" * (_MAX_ARTIFACT_BYTES + 1)

    with pytest.raises(_ReplayArtifactError, match=r"1048577 bytes; maximum is 1048576"):
        _parse_replay_artifact(data, source_name="large.chirp-replay")


def test_unknown_schema_and_kind_fail_with_actionable_versions() -> None:
    unknown_schema = _payload()
    unknown_schema["schema"] = "chirp.intent-timeline/2"
    with pytest.raises(_ReplayArtifactError, match=r"unsupported schema.*expected"):
        _parse_payload(unknown_schema)

    fixture_kind = _payload()
    fixture_kind["kind"] = "fixture"
    with pytest.raises(_ReplayArtifactError, match=r"unsupported artifact kind.*observation"):
        _parse_payload(fixture_kind)

    detail_kind = _payload()
    events = detail_kind["events"]
    assert isinstance(events, list)
    detail = events[0]["detail"]
    assert isinstance(detail, dict)
    detail["kind"] = "application-payload"
    with pytest.raises(_ReplayArtifactError, match="unsupported observation detail kind"):
        _parse_payload(detail_kind)


def test_forbidden_and_unknown_fields_fail_without_echoing_values() -> None:
    forbidden = _payload()
    events = forbidden["events"]
    assert isinstance(events, list)
    first = events[0]
    assert isinstance(first, dict)
    first["body"] = "sensitive-value-42"

    with pytest.raises(_ReplayArtifactError, match="forbidden field 'body'") as caught:
        _parse_payload(forbidden)
    assert "sensitive-value-42" not in str(caught.value)

    unknown = _payload()
    unknown["surprise"] = True
    with pytest.raises(_ReplayArtifactError, match="unexpected field 'surprise'"):
        _parse_payload(unknown)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda event: event.__setitem__("sequence", 9), "unique and contiguous"),
        (lambda event: event.__setitem__("sequence", 3), "unique and contiguous"),
        (lambda event: event.__setitem__("parent_sequence", 99), "parent must precede"),
        (lambda event: event.__setitem__("route_pattern", "/items?token=private"), "route pattern"),
    ],
)
def test_invalid_order_parent_and_route_pattern_fail_loud(mutate, message: str) -> None:
    payload = _payload()
    events = payload["events"]
    assert isinstance(events, list)
    event = events[3]
    assert isinstance(event, dict)
    mutate(event)

    with pytest.raises(_ReplayArtifactError, match=message):
        _parse_payload(payload)


def test_public_safe_scan_rejects_absolute_paths_and_secret_like_values() -> None:
    absolute = _payload()
    events = absolute["events"]
    assert isinstance(events, list)
    render = events[1]
    assert isinstance(render, dict)
    detail = render["detail"]
    assert isinstance(detail, dict)
    detail["template"] = "/Users/example/private.html"
    with pytest.raises(_ReplayArtifactError, match=r"absolute.*template paths"):
        _parse_payload(absolute)

    secret = _payload()
    events = secret["events"]
    assert isinstance(events, list)
    response = events[2]
    assert isinstance(response, dict)
    detail = response["detail"]
    assert isinstance(detail, dict)
    detail["target"] = "token=sensitive-value-42"
    with pytest.raises(_ReplayArtifactError, match="field class 'target'") as caught:
        _parse_payload(secret)
    assert "sensitive-value-42" not in str(caught.value)


def test_semantic_comparison_normalizes_only_documented_noise() -> None:
    expected = _parse_payload(_payload())
    actual_payload = _payload()
    created_with = actual_payload["created_with"]
    assert isinstance(created_with, dict)
    created_with["chirp"] = "0.10.99"
    capture = actual_payload["capture"]
    assert isinstance(capture, dict)
    capture["source"] = "debug-browser"
    events = actual_payload["events"]
    assert isinstance(events, list)
    for index, event in enumerate(events):
        assert isinstance(event, dict)
        event["elapsed_us"] = 50_000 + index
        if event["request_id"] is not None:
            event["request_id"] = "capture:" + "2" * 32

    comparison = _compare_replay_artifacts(expected, _parse_payload(actual_payload))

    assert comparison.matches
    assert comparison.differences == ()


def test_semantic_comparison_reports_status_mode_block_and_fingerprint_drift() -> None:
    expected = _parse_payload(_payload())
    actual_payload = _payload()
    application = actual_payload["application"]
    assert isinstance(application, dict)
    application["program_fingerprint"] = "sha256:" + "b" * 64
    events = actual_payload["events"]
    assert isinstance(events, list)
    request_detail = events[0]["detail"]
    render_detail = events[1]["detail"]
    response_detail = events[2]["detail"]
    assert isinstance(request_detail, dict)
    assert isinstance(render_detail, dict)
    assert isinstance(response_detail, dict)
    request_detail["request_mode"] = "boosted"
    render_detail["block"] = "summary"
    response_detail["status"] = 422

    comparison = _compare_replay_artifacts(expected, _parse_payload(actual_payload))
    fields = {difference.field for difference in comparison.differences}

    assert not comparison.matches
    assert "program_fingerprint" in fields
    assert "detail.request_mode" in fields
    assert "detail.block" in fields
    assert "detail.status" in fields


def test_semantic_comparison_reports_ordering_missing_and_truncation() -> None:
    expected = _parse_payload(_payload())

    reordered_payload = _payload()
    events = reordered_payload["events"]
    assert isinstance(events, list)
    diagnostic = events.pop()
    events.insert(0, diagnostic)
    for index, event in enumerate(events, 1):
        assert isinstance(event, dict)
        event["sequence"] = index
    # request -> render -> response -> SSE now occupy sequences 2..5.
    events[2]["parent_sequence"] = 2
    events[3]["parent_sequence"] = 3
    events[4]["parent_sequence"] = 4
    reordered = _compare_replay_artifacts(expected, _parse_payload(reordered_payload))
    assert any(difference.kind == "ordering" for difference in reordered.differences)

    truncated_payload = _payload()
    truncated_events = truncated_payload["events"]
    truncated_capture = truncated_payload["capture"]
    assert isinstance(truncated_events, list)
    assert isinstance(truncated_capture, dict)
    del truncated_events[:2]
    truncated_capture.update({"truncated": True, "dropped_count": 2, "first_retained_sequence": 3})
    truncated = _compare_replay_artifacts(expected, _parse_payload(truncated_payload))
    assert not truncated.matches
    assert any(difference.field == "truncated" for difference in truncated.differences)
    assert any(difference.kind == "missing" for difference in truncated.differences)

    added_payload = _payload()
    added_events = added_payload["events"]
    assert isinstance(added_events, list)
    extra = json.loads(json.dumps(added_events[-1]))
    extra["sequence"] = 6
    extra["detail"]["code"] = "extra-diagnostic"
    added_events.append(extra)
    added = _compare_replay_artifacts(expected, _parse_payload(added_payload))
    assert any(difference.kind == "added" for difference in added.differences)
