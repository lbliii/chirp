"""Structured logging with request correlation.

Provides request_id propagation via ContextVar and a structured_log helper
for JSON-formatted logs with request_id, user_id, path, etc.

When ``AppConfig.log_format == "json"`` the framework installs a crash-proof
:class:`JSONFormatter` on the ``"chirp"`` logger at freeze time
(:func:`configure_json_logging`) so Chirp's own log lines share the same JSON
envelope the server (Pounce) emits, instead of leaking the divergent ad-hoc
``json.dumps`` payload as an unformatted line.

This module is **internal** — it is intentionally absent from
``chirp.__all__`` / ``chirp._LAZY_IMPORTS`` and from ``docs/public-api.md``.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("chirp_request_id", default=None)

# Marker so configure_json_logging() is idempotent and never stacks handlers on
# the process-global "chirp" logger. Stored on the handler instance, not the
# logger, so a foreign handler installed by an app is never mistaken for ours.
_CHIRP_JSON_HANDLER_ATTR = "_chirp_json_handler"


def get_request_id() -> str | None:
    """Return the current request ID, or None if outside a request context."""
    return request_id_var.get()


def _current_trace_context() -> tuple[str, str] | None:
    """Best-effort (trace_id, span_id) hex pair from the active OTel span.

    Chirp has **no** opentelemetry dependency — OTel is delegated to the server
    (Pounce) via ``AppConfig.otel_endpoint``. This reads the ambient span behind
    a guarded import so logs join the trace pillar *when OTel is configured* and
    are unchanged otherwise. Returns ``None`` when opentelemetry is absent, no
    span is active, or the span context is invalid (the no-op default span).

    **SSE blind spot:** the SSE drain (:mod:`chirp.realtime.sse`) re-establishes
    request context from a captured snapshot and does **not** ``copy_context``,
    so the OTel span ContextVar does not survive that boundary — logs emitted
    from inside an ``EventStream`` generator carry no trace context even when one
    was active at connect time. Buffered responses and the ``Suspense`` / ``Stream``
    drains (which *do* ``copy_context``) keep the span for free.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    try:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if not ctx.is_valid:
            return None
        return (trace.format_trace_id(ctx.trace_id), trace.format_span_id(ctx.span_id))
    except Exception:
        # A misbehaving tracer must never take down request logging.
        return None


def structured_log(
    level: int,
    message: str,
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    path: str | None = None,
    method: str | None = None,
    **extra: Any,
) -> None:
    """Log a structured JSON message with correlation fields.

    Merges request_id from context if not provided. Use for audit trails
    and observability pipelines that expect JSON logs.

    When an OpenTelemetry span is active (configured via
    ``AppConfig.otel_endpoint``), ``trace_id`` and ``span_id`` are best-effort
    bound from :func:`opentelemetry.trace.get_current_span` so logs join the
    trace pillar. The lookup is fully guarded — no opentelemetry dependency, no
    failure surface. See :func:`_current_trace_context` for the SSE blind spot:
    trace context survives buffered, ``Suspense``, and ``Stream`` renders but
    **not** logs emitted from inside an SSE ``EventStream`` generator.
    """
    rid = request_id or get_request_id()
    payload: dict[str, Any] = {"message": message, **extra}
    if rid is not None:
        payload["request_id"] = rid
    if user_id is not None:
        payload["user_id"] = user_id
    if path is not None:
        payload["path"] = path
    if method is not None:
        payload["method"] = method
    trace_ctx = _current_trace_context()
    if trace_ctx is not None:
        payload["trace_id"], payload["span_id"] = trace_ctx
    logger = logging.getLogger("chirp")
    logger.log(level, json.dumps(payload, default=str))


class JSONFormatter(logging.Formatter):
    """Crash-proof JSON log formatter matching the server (Pounce) envelope.

    Produces ``{"ts", "level", "logger", "message"}`` (plus ``"exception"`` when
    the record carries ``exc_info``), the same shape Pounce's ``_JSONFormatter``
    emits, so Chirp's own ``"chirp"`` logger lines and the server's request lines
    parse identically in a log pipeline.

    Defensive by design: a record with a non-serializable extra, an exploding
    ``getMessage``, or an unformattable exception must never raise out of
    :meth:`format` (a logging handler that raises drops the log line *and* can
    surface the error at the call site). Every step degrades through a nested
    fallback to a minimal still-valid JSON object.
    """

    def format(self, record: logging.LogRecord) -> str:
        try:
            try:
                message = record.getMessage()
            except Exception:
                message = str(record.msg)
            entry: dict[str, Any] = {
                "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "level": record.levelname.lower(),
                "logger": record.name,
                "message": message,
            }
            if record.exc_info and record.exc_info[1]:
                try:
                    entry["exception"] = self.formatException(record.exc_info)
                except Exception:
                    entry["exception"] = repr(record.exc_info[1])
            return json.dumps(entry, default=str)
        except Exception:
            # Last-resort fallback: never raise, always emit parseable JSON.
            try:
                safe = str(getattr(record, "msg", ""))
            except Exception:
                safe = "<unrenderable log record>"
            return json.dumps({"level": "error", "logger": "chirp", "message": safe})


def configure_json_logging() -> None:
    """Install :class:`JSONFormatter` on the ``"chirp"`` logger, idempotently.

    Called once at app freeze when ``AppConfig.log_format == "json"`` so the
    framework's own logs match the server JSON shape. **Idempotent** — a second
    call is a no-op (the marker handler is detected and reused), so repeated
    ``freeze()`` calls or test re-runs never stack handlers on the process-global
    ``logging.Logger``.

    Scope discipline (free-threading / shared-state safety):

    - Mutates the ``"chirp"`` logger **only** — never ``logging.basicConfig``,
      which would clobber root configuration the server (Pounce) owns.
    - ``propagate = False`` so a chirp JSON line is not re-emitted through an
      ancestor handler (no double logging through Pounce's root handler).
    - Installs exactly one ``StreamHandler`` tagged with a private marker; a
      foreign handler an app added to the ``"chirp"`` logger is left untouched.
    """
    logger = logging.getLogger("chirp")
    for handler in logger.handlers:
        if getattr(handler, _CHIRP_JSON_HANDLER_ATTR, False):
            return
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    setattr(handler, _CHIRP_JSON_HANDLER_ATTR, True)
    logger.addHandler(handler)
    logger.propagate = False
