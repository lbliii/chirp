"""Private ordered observations for debug and test capture.

This module deliberately has no public export.  It stores only framework-owned,
structural facts copied from typed traces; request/response bodies, headers,
cookies, session data, rendered HTML, and template context never enter the
capture model.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import blake2b
from threading import Lock
from typing import Any, Literal

from chirp.templating.trace import ReturnTrace

_MAX_STRING_LENGTH = 512
_MAX_ITEMS = 16
_DEFAULT_RECORD_LIMIT = 500
_DEFAULT_BYTE_LIMIT = 1_048_576
_REQUEST_ID_PERSON = b"chirp-intent-id"

type _Channel = Literal["http", "sse", "diagnostic"]


def _bounded(value: str | None) -> str | None:
    if value is None or len(value) <= _MAX_STRING_LENGTH:
        return value
    return value[: _MAX_STRING_LENGTH - 3] + "..."


def _bounded_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_bounded(value) or "" for value in values[:_MAX_ITEMS])


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _optional_string(value: Any) -> str | None:
    return _bounded(value) if isinstance(value, str) else None


def _content_type_class(value: str | None) -> str | None:
    """Keep the media type while dropping header parameters such as boundaries."""
    if value is None:
        return None
    return _bounded(value.partition(";")[0].strip().lower())


def _capture_request_id(value: str | None) -> str | None:
    """Derive an opaque correlation ID without retaining a caller header value."""
    if value is None:
        return None
    digest = blake2b(
        value.encode("utf-8"),
        digest_size=16,
        person=_REQUEST_ID_PERSON,
    ).hexdigest()
    return f"capture:{digest}"


@dataclass(frozen=True, slots=True)
class _RequestObservation:
    """Structural request facts copied from a typed return trace."""

    method: str | None
    route_id: str | None
    request_mode: str | None
    mode_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RenderIntentObservation:
    """One typed render decision without template context or rendered HTML."""

    return_type: str
    category: str
    render_intent: str
    template: str | None
    block: str | None
    target: str | None
    swap: str | None
    streaming: bool
    sse: bool


@dataclass(frozen=True, slots=True)
class _ResponseObservation:
    """Final response and compiled-transition facts."""

    return_type: str
    category: str
    is_htmx: bool
    method: str | None
    request_content_type: str | None
    render_intent: str
    status: int | None
    template: str | None
    block: str | None
    target: str | None
    swap: str | None
    streaming: bool
    sse: bool
    observation_id: str | None
    route_id: str | None
    route_path: str | None
    request_mode: str | None
    mode_tags: tuple[str, ...]
    compiled_transition_ids: tuple[str, ...]
    transition_descriptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SSEObservation:
    """Allowlisted SSE lifecycle metadata; event data and IDs are excluded."""

    dialect: str | None = None
    heartbeat_interval: int | float | None = None
    retry_ms: int | None = None
    retry: int | None = None
    data_lines: int | None = None
    message_class: str | None = None
    value_type: str | None = None
    target: str | None = None
    swap: str | None = None
    during: str | None = None
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class _DiagnosticObservation:
    """Framework-owned diagnostic code with no arbitrary message payload."""

    code: str


type _ObservationDetail = (
    _RequestObservation
    | _RenderIntentObservation
    | _ResponseObservation
    | _SSEObservation
    | _DiagnosticObservation
)


@dataclass(frozen=True, slots=True)
class _ObservationDraft:
    """Immutable structural facts awaiting sequence allocation."""

    channel: _Channel
    phase: str
    route_pattern: str | None
    request_id: str | None
    parent_sequence: int | None
    internal: bool
    owner: str
    detail: _ObservationDetail
    parent_offset: int | None = None


@dataclass(frozen=True, slots=True)
class _IntentObservation:
    """One immutable observation in an authoritative capture order."""

    sequence: int
    elapsed_us: int
    ts_ms: int
    channel: _Channel
    phase: str
    route_pattern: str | None
    request_id: str | None
    parent_sequence: int | None
    internal: bool
    owner: str
    detail: _ObservationDetail


@dataclass(frozen=True, slots=True)
class _TruncationMarker:
    """Explicit evidence that a capture contains only a retained suffix."""

    dropped_count: int
    first_retained_sequence: int | None


@dataclass(frozen=True, slots=True)
class _CaptureSnapshot:
    """Stable read model for one capture lifecycle."""

    observations: tuple[_IntentObservation, ...]
    active: bool
    retained_bytes: int
    truncation: _TruncationMarker | None


class _IntentCapture:
    """Locked, bounded, process-local capture for debug/test use only."""

    __slots__ = (
        "_active",
        "_byte_limit",
        "_clock_ns",
        "_dropped_count",
        "_items",
        "_lock",
        "_next_sequence",
        "_record_limit",
        "_retained_bytes",
        "_sizes",
        "_start_ns",
        "_wall_clock_ns",
    )

    def __init__(
        self,
        *,
        record_limit: int = _DEFAULT_RECORD_LIMIT,
        byte_limit: int = _DEFAULT_BYTE_LIMIT,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        wall_clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        if record_limit < 1:
            msg = "record_limit must be at least 1"
            raise ValueError(msg)
        if byte_limit < 1:
            msg = "byte_limit must be at least 1"
            raise ValueError(msg)
        self._active = True
        self._byte_limit = byte_limit
        self._clock_ns = clock_ns
        self._dropped_count = 0
        self._items: deque[_IntentObservation] = deque()
        self._lock = Lock()
        self._next_sequence = 1
        self._record_limit = record_limit
        self._retained_bytes = 0
        self._sizes: deque[int] = deque()
        self._start_ns = clock_ns()
        self._wall_clock_ns = wall_clock_ns

    def publish(self, draft: _ObservationDraft) -> _IntentObservation:
        """Allocate and append one observation under one lock boundary."""
        return self.publish_many((draft,))[0]

    def publish_many(
        self,
        drafts: tuple[_ObservationDraft, ...],
    ) -> tuple[_IntentObservation, ...]:
        """Publish an ordered batch without interleaving concurrent writers."""
        if not drafts:
            return ()
        published: list[_IntentObservation] = []
        with self._lock:
            if not self._active:
                msg = "intent capture is closed"
                raise RuntimeError(msg)
            batch_start = self._next_sequence
            for draft in drafts:
                parent_sequence = draft.parent_sequence
                if parent_sequence is None and draft.parent_offset is not None:
                    parent_sequence = batch_start + draft.parent_offset
                observation = _IntentObservation(
                    sequence=self._next_sequence,
                    elapsed_us=max(0, (self._clock_ns() - self._start_ns) // 1_000),
                    ts_ms=self._wall_clock_ns() // 1_000_000,
                    channel=draft.channel,
                    phase=_bounded(draft.phase) or "unknown",
                    route_pattern=_bounded(draft.route_pattern),
                    request_id=_capture_request_id(draft.request_id),
                    parent_sequence=parent_sequence,
                    internal=draft.internal,
                    owner=_bounded(draft.owner) or "app",
                    detail=draft.detail,
                )
                self._next_sequence += 1
                size = _encoded_size(observation)
                self._items.append(observation)
                self._sizes.append(size)
                self._retained_bytes += size
                published.append(observation)
                self._truncate_to_bounds()
        return tuple(published)

    def snapshot(self, *, include_internal: bool = False) -> _CaptureSnapshot:
        """Return an immutable snapshot from one lock-consistent state."""
        with self._lock:
            all_items = tuple(self._items)
            marker = None
            if self._dropped_count:
                marker = _TruncationMarker(
                    dropped_count=self._dropped_count,
                    first_retained_sequence=(all_items[0].sequence if all_items else None),
                )
            active = self._active
            retained_bytes = self._retained_bytes
        observations = (
            all_items
            if include_internal
            else tuple(item for item in all_items if not item.internal)
        )
        return _CaptureSnapshot(
            observations=observations,
            active=active,
            retained_bytes=retained_bytes,
            truncation=marker,
        )

    def close(self) -> _CaptureSnapshot:
        """End publication for this capture without enabling later reuse."""
        with self._lock:
            self._active = False
        return self.snapshot(include_internal=True)

    def _truncate_to_bounds(self) -> None:
        while len(self._items) > self._record_limit or self._retained_bytes > self._byte_limit:
            self._items.popleft()
            self._retained_bytes -= self._sizes.popleft()
            self._dropped_count += 1


def _encoded_size(observation: _IntentObservation) -> int:
    """Return the canonical UTF-8 size used by the byte retention bound."""
    return len(
        json.dumps(
            _observation_mapping(observation),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _observation_mapping(observation: _IntentObservation) -> dict[str, Any]:
    """Build the existing debug-record shape plus ordered capture metadata."""
    return {
        "sequence": observation.sequence,
        "elapsed_us": observation.elapsed_us,
        "channel": observation.channel,
        "phase": observation.phase,
        "path": observation.route_pattern or "",
        "request_id": observation.request_id or "",
        "parent_sequence": observation.parent_sequence,
        "internal": observation.internal,
        "owner": observation.owner,
        "ts_ms": observation.ts_ms,
        "data": _detail_mapping(observation.detail),
    }


def _detail_mapping(detail: _ObservationDetail) -> dict[str, Any]:
    data = asdict(detail)
    result = {key: value for key, value in data.items() if value is not None}
    if isinstance(detail, _SSEObservation) and detail.data_lines is not None:
        # Preserve the current DevTools shape while deliberately discarding
        # application-controlled event names and IDs.
        result.update({"event": None, "id": None, "retry": detail.retry})
    return result


def _http_drafts(
    trace: ReturnTrace,
    *,
    request_id: str,
    internal: bool,
    owner: str,
) -> tuple[_ObservationDraft, _ObservationDraft, _ObservationDraft]:
    """Copy a typed trace into request, render, and response observations."""
    return (
        _ObservationDraft(
            channel="http",
            phase="request",
            route_pattern=trace.route_path,
            request_id=request_id,
            parent_sequence=None,
            internal=internal,
            owner=owner,
            detail=_RequestObservation(
                method=_bounded(trace.method),
                route_id=_bounded(trace.route_id),
                request_mode=_bounded(trace.request_mode),
                mode_tags=_bounded_tuple(trace.mode_tags),
            ),
        ),
        _ObservationDraft(
            channel="http",
            phase="render-intent",
            route_pattern=trace.route_path,
            request_id=request_id,
            parent_sequence=None,
            internal=internal,
            owner=owner,
            parent_offset=0,
            detail=_RenderIntentObservation(
                return_type=_bounded(trace.return_type) or "unknown",
                category=_bounded(trace.category) or "unknown",
                render_intent=_bounded(trace.render_intent) or "unknown",
                template=_bounded(trace.template),
                block=_bounded(trace.block),
                target=_bounded(trace.target),
                swap=_bounded(trace.swap),
                streaming=trace.streaming,
                sse=trace.sse,
            ),
        ),
        _ObservationDraft(
            channel="http",
            phase="response",
            route_pattern=trace.route_path,
            request_id=request_id,
            parent_sequence=None,
            internal=internal,
            owner=owner,
            parent_offset=1,
            detail=_ResponseObservation(
                return_type=_bounded(trace.return_type) or "unknown",
                category=_bounded(trace.category) or "unknown",
                is_htmx=trace.is_htmx,
                method=_bounded(trace.method),
                request_content_type=_content_type_class(trace.request_content_type),
                render_intent=_bounded(trace.render_intent) or "unknown",
                status=trace.status,
                template=_bounded(trace.template),
                block=_bounded(trace.block),
                target=_bounded(trace.target),
                swap=_bounded(trace.swap),
                streaming=trace.streaming,
                sse=trace.sse,
                observation_id=_bounded(trace.observation_id),
                route_id=_bounded(trace.route_id),
                route_path=_bounded(trace.route_path),
                request_mode=_bounded(trace.request_mode),
                mode_tags=_bounded_tuple(trace.mode_tags),
                compiled_transition_ids=_bounded_tuple(trace.compiled_transition_ids),
                transition_descriptions=_bounded_tuple(trace.transition_descriptions),
            ),
        ),
    )


def _sse_draft(
    *,
    phase: str,
    route_pattern: str,
    request_id: str,
    parent_sequence: int | None,
    internal: bool,
    owner: str,
    data: dict[str, Any] | None,
) -> _ObservationDraft:
    """Copy only allowlisted structural SSE metadata into an observation."""
    source = data or {}
    return _ObservationDraft(
        channel="sse",
        phase=phase,
        route_pattern=route_pattern,
        request_id=request_id,
        parent_sequence=parent_sequence,
        internal=internal,
        owner=owner,
        detail=_SSEObservation(
            dialect=_optional_string(source.get("dialect")),
            heartbeat_interval=_optional_number(source.get("heartbeat_interval")),
            retry_ms=_optional_int(source.get("retry_ms")),
            retry=_optional_int(source.get("retry")),
            data_lines=_optional_int(source.get("data_lines")),
            message_class=_optional_string(source.get("message_class")),
            value_type=_optional_string(source.get("value_type")),
            target=_optional_string(source.get("target")),
            swap=_optional_string(source.get("swap")),
            during=_optional_string(source.get("during")),
            error_type=_optional_string(source.get("error_type")),
        ),
    )


def _diagnostic_draft(code: str) -> _ObservationDraft:
    """Build a framework diagnostic without accepting arbitrary metadata."""
    return _ObservationDraft(
        channel="diagnostic",
        phase="diagnostic",
        route_pattern=None,
        request_id=None,
        parent_sequence=None,
        internal=False,
        owner="chirp",
        detail=_DiagnosticObservation(code=_bounded(code) or "unknown"),
    )
