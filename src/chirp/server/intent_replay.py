"""Private, data-only Intent Timeline artifact loading and comparison.

The ``.chirp-replay`` schema implemented here is deliberately private and has
no compatibility promise or public export.  Version 1 is UTF-8 JSON with this
exact envelope::

    {
      "schema": "chirp.intent-timeline/1",
      "kind": "observation",
      "created_with": {"chirp": "0.x"},
      "application": {"program_fingerprint": "sha256:..." | null},
      "capture": {
        "source": "debug-test",
        "redaction": "public-safe-v1",
        "truncated": false,
        "dropped_count": 0,
        "first_retained_sequence": null
      },
      "events": []
    }

Only fields represented by the frozen observation model are serialized.  The
allowlist contains structural request, render-intent, response, SSE lifecycle,
and diagnostic facts.  Bodies, HTML, headers, cookies, sessions, authorization,
query strings, concrete URLs, context, arbitrary notes, environment data, DSNs,
and absolute paths are forbidden.  The loader never imports an application,
opens a network connection, invokes a route, or mutates application state.

Semantic comparison ignores only documented nondeterminism: elapsed time,
opaque capture request IDs, per-event absolute sequence values, capture source,
and Chirp patch-version differences.  Route/mode, return/render intent, block/target,
status, compiled transitions, lifecycle facts, causal parents, ordering,
truncation, and program fingerprints remain authoritative.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, fields
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, Never, cast

from chirp.server.intent_timeline import (
    _CaptureSnapshot,
    _Channel,
    _DiagnosticObservation,
    _IntentObservation,
    _ObservationDetail,
    _RenderIntentObservation,
    _RequestObservation,
    _ResponseObservation,
    _SSEObservation,
)

_SCHEMA = "chirp.intent-timeline/1"
_KIND = "observation"
_REDACTION = "public-safe-v1"
_MAX_ARTIFACT_BYTES = 1_048_576
_MAX_EVENTS = 500
_MAX_STRING_LENGTH = 512
_MAX_ITEMS = 16
_MAX_DIFFERENCES = 64

_CAPTURE_ID_RE = re.compile(r"capture:[0-9a-f]{32}\Z")
_FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[A-Za-z0-9.+!-]*)\Z")
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]")
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:bearer\s+|(?:authorization|cookie|session(?:_id)?|csrf|password|secret|token)\s*[=:]|"
    r"(?:postgres(?:ql)?|redis|mysql)://|https?://|/(?:Users|home)/)"
)

_FORBIDDEN_FIELDS = frozenset(
    {
        "authorization",
        "body",
        "context",
        "context_keys",
        "cookie",
        "cookies",
        "csrf",
        "data",
        "dsn",
        "environment",
        "headers",
        "html",
        "query",
        "query_string",
        "request_body",
        "response_body",
        "session",
        "source_text",
        "url",
    }
)

type _DifferenceKind = Literal["metadata", "missing", "added", "ordering", "changed"]
type _Scalar = str | int | float | bool | None


class _ReplayArtifactError(ValueError):
    """A replay artifact failed strict schema or redaction validation."""


@dataclass(frozen=True, slots=True)
class _ReplayArtifact:
    """Validated private artifact with immutable typed observations."""

    chirp_version: str
    program_fingerprint: str | None
    source: str
    truncated: bool
    dropped_count: int
    first_retained_sequence: int | None
    observations: tuple[_IntentObservation, ...]


@dataclass(frozen=True, slots=True)
class _ReplayDifference:
    """One bounded semantic divergence without arbitrary source payloads."""

    kind: _DifferenceKind
    identity: str
    field: str
    expected: str | None
    actual: str | None


@dataclass(frozen=True, slots=True)
class _ReplayComparison:
    """Deterministic semantic comparison result."""

    matches: bool
    differences: tuple[_ReplayDifference, ...]


@dataclass(frozen=True, slots=True)
class _ParseContext:
    source_name: str


def _dump_replay_artifact(
    snapshot: _CaptureSnapshot,
    *,
    chirp_version: str,
    program_fingerprint: str | None,
    source: str = "debug-test",
) -> bytes:
    """Serialize one allowlisted capture snapshot to canonical UTF-8 JSON."""
    marker = snapshot.truncation
    payload: dict[str, Any] = {
        "schema": _SCHEMA,
        "kind": _KIND,
        "created_with": {"chirp": chirp_version},
        "application": {"program_fingerprint": program_fingerprint},
        "capture": {
            "source": source,
            "redaction": _REDACTION,
            "truncated": marker is not None,
            "dropped_count": marker.dropped_count if marker is not None else 0,
            "first_retained_sequence": (
                marker.first_retained_sequence if marker is not None else None
            ),
        },
        "events": [_event_mapping(item) for item in snapshot.observations],
    }
    try:
        encoded = (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:  # defensive: model is typed
        msg = "generated replay artifact contains a non-JSON structural value"
        raise _ReplayArtifactError(msg) from exc
    # Parse our own output through the same untrusted-input gate.  This keeps
    # serialization and loading on one schema/redaction authority.
    _parse_replay_artifact(encoded, source_name="<generated .chirp-replay>")
    return encoded


def _load_replay_artifact(path: Path) -> _ReplayArtifact:
    """Read and strictly validate a private ``.chirp-replay`` artifact."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        msg = f"{path}: unable to read replay artifact: {exc}"
        raise _ReplayArtifactError(msg) from exc
    return _parse_replay_artifact(data, source_name=str(path))


def _parse_replay_artifact(data: bytes, *, source_name: str) -> _ReplayArtifact:
    """Validate untrusted artifact bytes without importing or executing code."""
    context = _ParseContext(source_name=source_name)
    if len(data) > _MAX_ARTIFACT_BYTES:
        _fail(
            context,
            "$",
            f"artifact is {len(data)} bytes; maximum is {_MAX_ARTIFACT_BYTES}",
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail(context, "$", f"artifact is not valid UTF-8 at byte {exc.start}")
    try:
        raw = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        _fail(context, "$", f"invalid JSON: {exc}")

    root = _strict_object(
        context,
        raw,
        "$",
        {"schema", "kind", "created_with", "application", "capture", "events"},
    )
    schema = _required_string(context, root["schema"], "$.schema")
    if schema != _SCHEMA:
        _fail(context, "$.schema", f"unsupported schema {schema!r}; expected {_SCHEMA!r}")
    kind = _required_string(context, root["kind"], "$.kind")
    if kind != _KIND:
        _fail(context, "$.kind", f"unsupported artifact kind {kind!r}; expected {_KIND!r}")

    created_with = _strict_object(
        context,
        root["created_with"],
        "$.created_with",
        {"chirp"},
    )
    chirp_version = _required_string(
        context,
        created_with["chirp"],
        "$.created_with.chirp",
    )
    if not _VERSION_RE.fullmatch(chirp_version):
        _fail(context, "$.created_with.chirp", "must be a bounded PEP 440-style version")

    application = _strict_object(
        context,
        root["application"],
        "$.application",
        {"program_fingerprint"},
    )
    program_fingerprint = _optional_string(
        context,
        application["program_fingerprint"],
        "$.application.program_fingerprint",
    )
    if program_fingerprint is not None and not _FINGERPRINT_RE.fullmatch(program_fingerprint):
        _fail(
            context,
            "$.application.program_fingerprint",
            "must be null or sha256 followed by 64 lowercase hexadecimal digits",
        )

    capture = _strict_object(
        context,
        root["capture"],
        "$.capture",
        {
            "source",
            "redaction",
            "truncated",
            "dropped_count",
            "first_retained_sequence",
        },
    )
    source = _required_string(context, capture["source"], "$.capture.source")
    if not _TOKEN_RE.fullmatch(source):
        _fail(context, "$.capture.source", "must be a lowercase structural token")
    redaction = _required_string(context, capture["redaction"], "$.capture.redaction")
    if redaction != _REDACTION:
        _fail(
            context,
            "$.capture.redaction",
            f"unsupported redaction profile {redaction!r}; expected {_REDACTION!r}",
        )
    truncated = _required_bool(context, capture["truncated"], "$.capture.truncated")
    dropped_count = _required_int(
        context,
        capture["dropped_count"],
        "$.capture.dropped_count",
        minimum=0,
    )
    first_retained_sequence = _optional_int(
        context,
        capture["first_retained_sequence"],
        "$.capture.first_retained_sequence",
        minimum=1,
    )

    raw_events = root["events"]
    if not isinstance(raw_events, list):
        _fail(context, "$.events", "must be an array")
    if len(raw_events) > _MAX_EVENTS:
        _fail(context, "$.events", f"contains {len(raw_events)} events; maximum is {_MAX_EVENTS}")
    observations = tuple(
        _parse_event(context, item, f"$.events[{index}]") for index, item in enumerate(raw_events)
    )
    _validate_capture(
        context,
        observations,
        truncated=truncated,
        dropped_count=dropped_count,
        first_retained_sequence=first_retained_sequence,
    )
    return _ReplayArtifact(
        chirp_version=chirp_version,
        program_fingerprint=program_fingerprint,
        source=source,
        truncated=truncated,
        dropped_count=dropped_count,
        first_retained_sequence=first_retained_sequence,
        observations=observations,
    )


def _compare_replay_artifacts(
    expected: _ReplayArtifact,
    actual: _ReplayArtifact,
) -> _ReplayComparison:
    """Compare structural semantics while ignoring documented capture noise."""
    differences: list[_ReplayDifference] = []

    def add(
        kind: _DifferenceKind,
        identity: str,
        field: str,
        expected_value: Any,
        actual_value: Any,
    ) -> None:
        if len(differences) >= _MAX_DIFFERENCES:
            return
        differences.append(
            _ReplayDifference(
                kind=kind,
                identity=identity,
                field=field,
                expected=_display(expected_value),
                actual=_display(actual_value),
            )
        )

    if _major_minor(expected.chirp_version) != _major_minor(actual.chirp_version):
        add(
            "metadata",
            "artifact",
            "created_with.chirp.major_minor",
            _major_minor(expected.chirp_version),
            _major_minor(actual.chirp_version),
        )
    for field_name in (
        "program_fingerprint",
        "truncated",
        "dropped_count",
        "first_retained_sequence",
    ):
        expected_value = getattr(expected, field_name)
        actual_value = getattr(actual, field_name)
        if expected_value != actual_value:
            add("metadata", "artifact", field_name, expected_value, actual_value)

    expected_index = _event_index(expected)
    actual_index = _event_index(actual)
    expected_order = tuple(expected_index)
    actual_order = tuple(actual_index)
    if Counter(expected_order) == Counter(actual_order) and expected_order != actual_order:
        add("ordering", "events", "order", expected_order, actual_order)

    for identity in expected_order:
        if identity not in actual_index:
            add("missing", identity, "event", "present", None)
    for identity in actual_order:
        if identity not in expected_index:
            add("added", identity, "event", None, "present")

    expected_parent_ids = _sequence_identities(expected_index)
    actual_parent_ids = _sequence_identities(actual_index)
    for identity in expected_order:
        if identity not in actual_index:
            continue
        expected_event = expected_index[identity]
        actual_event = actual_index[identity]
        expected_fields = _flatten_mapping(
            _semantic_event(expected_event, expected_parent_ids, expected),
        )
        actual_fields = _flatten_mapping(
            _semantic_event(actual_event, actual_parent_ids, actual),
        )
        for field_name in sorted(expected_fields.keys() | actual_fields.keys()):
            expected_value = expected_fields.get(field_name)
            actual_value = actual_fields.get(field_name)
            if expected_value != actual_value:
                add("changed", identity, field_name, expected_value, actual_value)

    return _ReplayComparison(matches=not differences, differences=tuple(differences))


def _event_mapping(observation: _IntentObservation) -> dict[str, Any]:
    return {
        "sequence": observation.sequence,
        "elapsed_us": observation.elapsed_us,
        "channel": observation.channel,
        "phase": observation.phase,
        "route_pattern": observation.route_pattern,
        "request_id": observation.request_id,
        "parent_sequence": observation.parent_sequence,
        "internal": observation.internal,
        "owner": observation.owner,
        "detail": _artifact_detail_mapping(observation.detail),
    }


def _artifact_detail_mapping(detail: _ObservationDetail) -> dict[str, Any]:
    if isinstance(detail, _RequestObservation):
        kind = "request"
    elif isinstance(detail, _RenderIntentObservation):
        kind = "render-intent"
    elif isinstance(detail, _ResponseObservation):
        kind = "response"
    elif isinstance(detail, _SSEObservation):
        kind = "sse"
    else:
        kind = "diagnostic"
    return {"kind": kind, **asdict(detail)}


def _parse_event(
    context: _ParseContext,
    value: Any,
    path: str,
) -> _IntentObservation:
    event = _strict_object(
        context,
        value,
        path,
        {
            "sequence",
            "elapsed_us",
            "channel",
            "phase",
            "route_pattern",
            "request_id",
            "parent_sequence",
            "internal",
            "owner",
            "detail",
        },
    )
    sequence = _required_int(context, event["sequence"], f"{path}.sequence", minimum=1)
    elapsed_us = _required_int(
        context,
        event["elapsed_us"],
        f"{path}.elapsed_us",
        minimum=0,
    )
    channel = _required_string(context, event["channel"], f"{path}.channel")
    if channel not in {"http", "sse", "diagnostic"}:
        _fail(context, f"{path}.channel", f"unsupported channel {channel!r}")
    typed_channel = cast(_Channel, channel)
    phase = _safe_required_string(context, event["phase"], f"{path}.phase", "phase")
    route_pattern = _safe_optional_string(
        context,
        event["route_pattern"],
        f"{path}.route_pattern",
        "route_pattern",
    )
    request_id = _optional_string(context, event["request_id"], f"{path}.request_id")
    if request_id is not None and not _CAPTURE_ID_RE.fullmatch(request_id):
        _fail(context, f"{path}.request_id", "must be an opaque capture correlation ID")
    parent_sequence = _optional_int(
        context,
        event["parent_sequence"],
        f"{path}.parent_sequence",
        minimum=1,
    )
    internal = _required_bool(context, event["internal"], f"{path}.internal")
    owner = _safe_required_string(context, event["owner"], f"{path}.owner", "owner")
    detail = _parse_detail(context, event["detail"], f"{path}.detail")
    return _IntentObservation(
        sequence=sequence,
        elapsed_us=elapsed_us,
        ts_ms=0,  # absolute wall-clock time is intentionally not persisted
        channel=typed_channel,
        phase=phase,
        route_pattern=route_pattern,
        request_id=request_id,
        parent_sequence=parent_sequence,
        internal=internal,
        owner=owner,
        detail=detail,
    )


def _parse_detail(
    context: _ParseContext,
    value: Any,
    path: str,
) -> _ObservationDetail:
    if not isinstance(value, dict):
        _fail(context, path, "must be an object")
    kind_value = value.get("kind")
    kind = _required_string(context, kind_value, f"{path}.kind")
    if kind == "request":
        item = _strict_detail(context, value, path, _RequestObservation)
        return _RequestObservation(
            method=_safe_optional_string(context, item["method"], f"{path}.method", "method"),
            route_id=_safe_optional_string(
                context, item["route_id"], f"{path}.route_id", "route_id"
            ),
            request_mode=_safe_optional_string(
                context,
                item["request_mode"],
                f"{path}.request_mode",
                "request_mode",
            ),
            mode_tags=_string_tuple(context, item["mode_tags"], f"{path}.mode_tags", "mode_tag"),
        )
    if kind == "render-intent":
        item = _strict_detail(context, value, path, _RenderIntentObservation)
        return _RenderIntentObservation(
            return_type=_safe_required_string(
                context, item["return_type"], f"{path}.return_type", "return_type"
            ),
            category=_safe_required_string(
                context, item["category"], f"{path}.category", "category"
            ),
            render_intent=_safe_required_string(
                context,
                item["render_intent"],
                f"{path}.render_intent",
                "render_intent",
            ),
            template=_safe_optional_string(
                context, item["template"], f"{path}.template", "template"
            ),
            block=_safe_optional_string(context, item["block"], f"{path}.block", "block"),
            target=_safe_optional_string(context, item["target"], f"{path}.target", "target"),
            swap=_safe_optional_string(context, item["swap"], f"{path}.swap", "swap"),
            streaming=_required_bool(context, item["streaming"], f"{path}.streaming"),
            sse=_required_bool(context, item["sse"], f"{path}.sse"),
        )
    if kind == "response":
        item = _strict_detail(context, value, path, _ResponseObservation)
        return _ResponseObservation(
            return_type=_safe_required_string(
                context, item["return_type"], f"{path}.return_type", "return_type"
            ),
            category=_safe_required_string(
                context, item["category"], f"{path}.category", "category"
            ),
            is_htmx=_required_bool(context, item["is_htmx"], f"{path}.is_htmx"),
            method=_safe_optional_string(context, item["method"], f"{path}.method", "method"),
            request_content_type=_content_type(
                context,
                item["request_content_type"],
                f"{path}.request_content_type",
            ),
            render_intent=_safe_required_string(
                context,
                item["render_intent"],
                f"{path}.render_intent",
                "render_intent",
            ),
            status=_optional_int(context, item["status"], f"{path}.status", minimum=100),
            template=_safe_optional_string(
                context, item["template"], f"{path}.template", "template"
            ),
            block=_safe_optional_string(context, item["block"], f"{path}.block", "block"),
            target=_safe_optional_string(context, item["target"], f"{path}.target", "target"),
            swap=_safe_optional_string(context, item["swap"], f"{path}.swap", "swap"),
            streaming=_required_bool(context, item["streaming"], f"{path}.streaming"),
            sse=_required_bool(context, item["sse"], f"{path}.sse"),
            observation_id=_safe_optional_string(
                context,
                item["observation_id"],
                f"{path}.observation_id",
                "observation_id",
            ),
            route_id=_safe_optional_string(
                context, item["route_id"], f"{path}.route_id", "route_id"
            ),
            route_path=_safe_optional_string(
                context, item["route_path"], f"{path}.route_path", "route_pattern"
            ),
            request_mode=_safe_optional_string(
                context,
                item["request_mode"],
                f"{path}.request_mode",
                "request_mode",
            ),
            mode_tags=_string_tuple(context, item["mode_tags"], f"{path}.mode_tags", "mode_tag"),
            compiled_transition_ids=_string_tuple(
                context,
                item["compiled_transition_ids"],
                f"{path}.compiled_transition_ids",
                "transition_id",
            ),
            transition_descriptions=_string_tuple(
                context,
                item["transition_descriptions"],
                f"{path}.transition_descriptions",
                "transition_description",
            ),
        )
    if kind == "sse":
        item = _strict_detail(context, value, path, _SSEObservation)
        return _SSEObservation(
            dialect=_safe_optional_string(context, item["dialect"], f"{path}.dialect", "dialect"),
            heartbeat_interval=_optional_number(
                context,
                item["heartbeat_interval"],
                f"{path}.heartbeat_interval",
                minimum=0,
            ),
            retry_ms=_optional_int(context, item["retry_ms"], f"{path}.retry_ms", minimum=0),
            retry=_optional_int(context, item["retry"], f"{path}.retry", minimum=0),
            data_lines=_optional_int(context, item["data_lines"], f"{path}.data_lines", minimum=0),
            message_class=_safe_optional_string(
                context,
                item["message_class"],
                f"{path}.message_class",
                "message_class",
            ),
            value_type=_safe_optional_string(
                context, item["value_type"], f"{path}.value_type", "value_type"
            ),
            target=_safe_optional_string(context, item["target"], f"{path}.target", "target"),
            swap=_safe_optional_string(context, item["swap"], f"{path}.swap", "swap"),
            during=_safe_optional_string(context, item["during"], f"{path}.during", "during"),
            error_type=_safe_optional_string(
                context, item["error_type"], f"{path}.error_type", "error_type"
            ),
        )
    if kind == "diagnostic":
        item = _strict_detail(context, value, path, _DiagnosticObservation)
        return _DiagnosticObservation(
            code=_safe_required_string(context, item["code"], f"{path}.code", "code")
        )
    _fail(context, f"{path}.kind", f"unsupported observation detail kind {kind!r}")


def _strict_detail(
    context: _ParseContext,
    value: dict[str, Any],
    path: str,
    detail_type: type,
) -> dict[str, Any]:
    allowed = {"kind", *(field.name for field in fields(detail_type))}
    return _strict_object(context, value, path, allowed)


def _validate_capture(
    context: _ParseContext,
    observations: tuple[_IntentObservation, ...],
    *,
    truncated: bool,
    dropped_count: int,
    first_retained_sequence: int | None,
) -> None:
    if not truncated and (dropped_count != 0 or first_retained_sequence is not None):
        _fail(
            context,
            "$.capture",
            "non-truncated capture must have dropped_count=0 and first_retained_sequence=null",
        )
    if truncated and dropped_count < 1:
        _fail(context, "$.capture.dropped_count", "truncated capture must drop at least one event")
    if not observations:
        if first_retained_sequence is not None:
            _fail(
                context,
                "$.capture.first_retained_sequence",
                "must be null when no events are retained",
            )
        return

    sequences = tuple(item.sequence for item in observations)
    first = sequences[0]
    if not truncated and first != 1:
        _fail(context, "$.events[0].sequence", "complete capture must start at sequence 1")
    if truncated:
        if first_retained_sequence != first:
            _fail(
                context,
                "$.capture.first_retained_sequence",
                "must equal the first retained event sequence",
            )
        if dropped_count != first - 1:
            _fail(
                context,
                "$.capture.dropped_count",
                "must equal the number of sequence values before the retained suffix",
            )
    for index, (previous, current) in enumerate(pairwise(sequences), 1):
        if current != previous + 1:
            _fail(
                context,
                f"$.events[{index}].sequence",
                "sequence values must be unique and contiguous",
            )

    retained = set(sequences)
    for index, observation in enumerate(observations):
        parent = observation.parent_sequence
        if parent is None:
            continue
        if parent >= observation.sequence:
            _fail(
                context,
                f"$.events[{index}].parent_sequence",
                "parent must precede its child",
            )
        if parent not in retained and not (truncated and parent < first):
            _fail(
                context,
                f"$.events[{index}].parent_sequence",
                "parent must reference a retained earlier event",
            )


def _strict_object(
    context: _ParseContext,
    value: Any,
    path: str,
    allowed: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(context, path, "must be an object")
    if not all(isinstance(key, str) for key in value):
        _fail(context, path, "object keys must be strings")
    mapping = cast(dict[str, Any], value)
    keys = set(mapping)
    for key in keys:
        if key.lower() in _FORBIDDEN_FIELDS:
            _fail(
                context,
                f"{path}.{key}",
                f"forbidden field {key!r}; artifacts accept structural metadata only",
            )
    extra = keys - allowed
    if extra:
        key = sorted(extra)[0]
        _fail(context, f"{path}.{key}", f"unexpected field {key!r}")
    missing = allowed - keys
    if missing:
        key = sorted(missing)[0]
        _fail(context, path, f"missing required field {key!r}")
    return mapping


def _required_string(context: _ParseContext, value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail(context, path, "must be a string")
    if not value:
        _fail(context, path, "must not be empty")
    if len(value) > _MAX_STRING_LENGTH:
        _fail(context, path, f"string exceeds {_MAX_STRING_LENGTH} characters")
    return value


def _optional_string(context: _ParseContext, value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _required_string(context, value, path)


def _safe_required_string(
    context: _ParseContext,
    value: Any,
    path: str,
    field_name: str,
) -> str:
    result = _required_string(context, value, path)
    _validate_public_safe_string(context, result, path, field_name)
    return result


def _safe_optional_string(
    context: _ParseContext,
    value: Any,
    path: str,
    field_name: str,
) -> str | None:
    result = _optional_string(context, value, path)
    if result is not None:
        _validate_public_safe_string(context, result, path, field_name)
    return result


def _validate_public_safe_string(
    context: _ParseContext,
    value: str,
    path: str,
    field_name: str,
) -> None:
    if any(ord(character) < 32 for character in value):
        _fail(context, path, "contains a control character")
    if "<" in value or ">" in value:
        _fail(context, path, f"field class {field_name!r} contains HTML-like markup")
    if field_name == "route_pattern":
        route_parts = value.split("/")
        if (
            not value.startswith("/")
            or "?" in value
            or "#" in value
            or "://" in value
            or ".." in route_parts
        ):
            _fail(context, path, "must be a route pattern without query, fragment, or origin")
        if _EMAIL_RE.search(value) or _SECRET_VALUE_RE.search(value):
            _fail(context, path, "route pattern failed the public-safe scan")
        return
    if field_name == "template":
        template_parts = value.replace("\\", "/").split("/")
        if (
            value.startswith(("/", "\\"))
            or _WINDOWS_PATH_RE.search(value)
            or ".." in template_parts
        ):
            _fail(context, path, "absolute and parent-relative template paths are forbidden")
    if _EMAIL_RE.search(value) or _SECRET_VALUE_RE.search(value):
        _fail(context, path, f"field class {field_name!r} failed the public-safe scan")


def _string_tuple(
    context: _ParseContext,
    value: Any,
    path: str,
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        _fail(context, path, "must be an array of strings")
    if len(value) > _MAX_ITEMS:
        _fail(context, path, f"contains {len(value)} items; maximum is {_MAX_ITEMS}")
    return tuple(
        _safe_required_string(context, item, f"{path}[{index}]", field_name)
        for index, item in enumerate(value)
    )


def _required_bool(context: _ParseContext, value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(context, path, "must be a boolean")
    return value


def _required_int(
    context: _ParseContext,
    value: Any,
    path: str,
    *,
    minimum: int,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _fail(context, path, "must be an integer")
    if value < minimum:
        _fail(context, path, f"must be at least {minimum}")
    return value


def _optional_int(
    context: _ParseContext,
    value: Any,
    path: str,
    *,
    minimum: int,
) -> int | None:
    if value is None:
        return None
    return _required_int(context, value, path, minimum=minimum)


def _optional_number(
    context: _ParseContext,
    value: Any,
    path: str,
    *,
    minimum: float,
) -> int | float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        _fail(context, path, "must be a finite number or null")
    if value < minimum:
        _fail(context, path, f"must be at least {minimum}")
    return value


def _content_type(context: _ParseContext, value: Any, path: str) -> str | None:
    result = _safe_optional_string(context, value, path, "request_content_type")
    if result is not None and (";" in result or "/" not in result):
        _fail(context, path, "must contain only a media type without header parameters")
    return result


def _reject_json_constant(value: str) -> None:
    msg = f"non-finite JSON number {value!r} is forbidden"
    raise ValueError(msg)


def _fail(context: _ParseContext, path: str, message: str) -> Never:
    raise _ReplayArtifactError(f"{context.source_name}: {path}: {message}")


def _event_index(artifact: _ReplayArtifact) -> dict[str, _IntentObservation]:
    occurrences: defaultdict[str, int] = defaultdict(int)
    indexed: dict[str, _IntentObservation] = {}
    for observation in artifact.observations:
        base = f"{observation.channel}:{observation.phase}:{observation.route_pattern or '<none>'}"
        occurrences[base] += 1
        indexed[f"{base}#{occurrences[base]}"] = observation
    return indexed


def _sequence_identities(indexed: dict[str, _IntentObservation]) -> dict[int, str]:
    return {observation.sequence: identity for identity, observation in indexed.items()}


def _semantic_event(
    observation: _IntentObservation,
    sequence_identities: dict[int, str],
    artifact: _ReplayArtifact,
) -> dict[str, Any]:
    parent: str | None = None
    if observation.parent_sequence is not None:
        parent = sequence_identities.get(observation.parent_sequence)
        if parent is None and artifact.truncated:
            parent = "<before-retained>"
    return {
        "channel": observation.channel,
        "phase": observation.phase,
        "route_pattern": observation.route_pattern,
        "parent": parent,
        "internal": observation.internal,
        "owner": observation.owner,
        "detail": _artifact_detail_mapping(observation.detail),
    }


def _flatten_mapping(value: dict[str, Any], prefix: str = "") -> dict[str, _Scalar | tuple]:
    flattened: dict[str, _Scalar | tuple] = {}
    for key, item in value.items():
        field = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            flattened.update(_flatten_mapping(item, field))
        elif isinstance(item, list):
            flattened[field] = tuple(item)
        else:
            flattened[field] = item
    return flattened


def _major_minor(version: str) -> str:
    match = re.match(r"([0-9]+)\.([0-9]+)", version)
    return f"{match.group(1)}.{match.group(2)}" if match is not None else version


def _display(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, tuple):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)
