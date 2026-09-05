"""Best-effort OpenTelemetry spans for Chirp internals.

Chirp has **no** hard dependency on ``opentelemetry`` — OTel is configured
through Pounce via ``AppConfig.otel_endpoint``. These helpers no-op when the
SDK is absent or misbehaving, matching :mod:`chirp.logging`'s guarded pattern.
"""

from __future__ import annotations

import contextlib
import time
from types import TracebackType
from typing import Any


def trace_span(name: str, /, **attributes: Any) -> _TraceSpan:
    """Open a best-effort OTel span without mutating raised exceptions.

    Enters a :class:`_SpanScope` when OTel is available, else ``None``.
    Records ``duration_ms`` on close and marks ERROR status when the block
    raises, preserving the original exception and traceback.
    """
    return _TraceSpan(name, attributes)


class _TraceSpan:
    """Class-based exit avoids contextlib assigning frozen error tracebacks."""

    __slots__ = ("_attributes", "_name", "_scope")

    def __init__(self, name: str, attributes: dict[str, Any]) -> None:
        self._name = name
        self._attributes = attributes
        self._scope: _SpanScope | None = None

    def __enter__(self) -> _SpanScope | None:
        self._scope = _SpanScope.start(self._name, **self._attributes)
        return self._scope

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._scope is not None:
            self._scope.close(error=exc)


class _SpanScope:
    """Manual span lifetime — use for async generators where ``with`` ends too early."""

    __slots__ = ("_span", "_start", "_token")

    def __init__(
        self,
        span: Any,
        start: float,
        token: Any,
    ) -> None:
        self._span = span
        self._start = start
        self._token = token

    @classmethod
    def start(cls, name: str, /, **attributes: Any) -> _SpanScope | None:
        try:
            from opentelemetry import trace
        except ImportError:
            return None
        try:
            tracer = trace.get_tracer("chirp")
            span = tracer.start_span(name)
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
            token = trace.use_span(span, end_on_exit=False)
            token.__enter__()
            return cls(span, time.monotonic(), token)
        except Exception:
            return None

    def set_attribute(self, key: str, value: Any) -> None:
        if self._span is not None and value is not None:
            with contextlib.suppress(Exception):
                self._span.set_attribute(key, value)

    def close(
        self,
        *,
        error: BaseException | None = None,
        **extra_attributes: Any,
    ) -> None:
        if self._span is None:
            return
        duration_ms = (time.monotonic() - self._start) * 1000.0
        with contextlib.suppress(Exception):
            self._span.set_attribute("duration_ms", duration_ms)
            for key, value in extra_attributes.items():
                if value is not None:
                    self._span.set_attribute(key, value)
            if error is not None:
                self._span.record_exception(error)
                from opentelemetry.trace import Status, StatusCode

                self._span.set_status(Status(StatusCode.ERROR, str(error)))
            if self._token is not None:
                self._token.__exit__(None, None, None)
            self._span.end()
