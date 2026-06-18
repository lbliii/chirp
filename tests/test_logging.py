"""Tests for chirp.logging structured logging hardening (issue #379).

Covers two internal hardening changes:

1. ``structured_log`` best-effort binds ``trace_id`` / ``span_id`` from the
   active OpenTelemetry span behind a guarded import (chirp has no opentelemetry
   dependency). opentelemetry is not installed in the dev env, so a valid span
   is simulated by injecting a fake ``opentelemetry`` package into
   ``sys.modules``.
2. ``log_format == "json"`` installs a crash-proof ``JSONFormatter`` on the
   ``"chirp"`` logger at freeze, matching the server (Pounce) JSON envelope.
"""

from __future__ import annotations

import json
import logging
import sys
import types
from typing import Any

import pytest

from chirp import App
from chirp.config import AppConfig
from chirp.logging import (
    JSONFormatter,
    _current_trace_context,
    configure_json_logging,
    structured_log,
)
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Fake opentelemetry injection
# ---------------------------------------------------------------------------

# Sentinels matching what the SDK would produce for a real span; the formatter
# functions format_trace_id/format_span_id zero-pad to 32/16 hex chars.
_TRACE_ID = 0x0AF7651916CD43DD8448EB211C80319C
_SPAN_ID = 0xB7AD6B7169203331
_TRACE_ID_HEX = "0af7651916cd43dd8448eb211c80319c"
_SPAN_ID_HEX = "b7ad6b7169203331"


def _install_fake_otel(monkeypatch: pytest.MonkeyPatch, *, valid: bool) -> None:
    """Inject a minimal fake ``opentelemetry.trace`` into ``sys.modules``.

    ``valid`` toggles ``SpanContext.is_valid`` so we can exercise both the
    enriched path and the invalid-span (no-op default span) skip path.
    """

    class _SpanContext:
        trace_id = _TRACE_ID
        span_id = _SPAN_ID
        is_valid = valid

    class _Span:
        def get_span_context(self) -> _SpanContext:
            return _SpanContext()

    trace_mod = types.ModuleType("opentelemetry.trace")
    trace_mod.get_current_span = lambda: _Span()  # type: ignore[attr-defined]
    trace_mod.format_trace_id = lambda tid: format(tid, "032x")  # type: ignore[attr-defined]
    trace_mod.format_span_id = lambda sid: format(sid, "016x")  # type: ignore[attr-defined]

    otel_pkg = types.ModuleType("opentelemetry")
    otel_pkg.trace = trace_mod  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "opentelemetry", otel_pkg)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_mod)


# ---------------------------------------------------------------------------
# Trace-context enrichment
# ---------------------------------------------------------------------------


class TestTraceContext:
    def test_no_otel_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guarded ImportError path: opentelemetry absent → no trace context."""
        monkeypatch.setitem(sys.modules, "opentelemetry", None)
        assert _current_trace_context() is None

    def test_valid_span_returns_hex_pair(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_otel(monkeypatch, valid=True)
        assert _current_trace_context() == (_TRACE_ID_HEX, _SPAN_ID_HEX)

    def test_invalid_span_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The no-op default span (is_valid False) is skipped, never emitted."""
        _install_fake_otel(monkeypatch, valid=False)
        assert _current_trace_context() is None

    def test_misbehaving_tracer_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        trace_mod = types.ModuleType("opentelemetry.trace")

        def _boom() -> Any:
            raise RuntimeError("tracer exploded")

        trace_mod.get_current_span = _boom  # type: ignore[attr-defined]
        otel_pkg = types.ModuleType("opentelemetry")
        otel_pkg.trace = trace_mod  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "opentelemetry", otel_pkg)
        monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_mod)
        assert _current_trace_context() is None

    def test_structured_log_emits_trace_fields_when_span_active(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _install_fake_otel(monkeypatch, valid=True)
        with caplog.at_level(logging.INFO, logger="chirp"):
            structured_log(logging.INFO, "hello", path="/x", method="GET")
        payload = json.loads(caplog.records[-1].getMessage())
        assert payload["message"] == "hello"
        assert payload["trace_id"] == _TRACE_ID_HEX
        assert payload["span_id"] == _SPAN_ID_HEX

    def test_structured_log_omits_trace_fields_when_otel_absent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setitem(sys.modules, "opentelemetry", None)
        with caplog.at_level(logging.INFO, logger="chirp"):
            structured_log(logging.INFO, "hello")
        payload = json.loads(caplog.records[-1].getMessage())
        assert "trace_id" not in payload
        assert "span_id" not in payload


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------


class TestJSONFormatter:
    def test_normal_record_is_parseable_server_envelope(self) -> None:
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="chirp",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="plain message",
            args=(),
            exc_info=None,
        )
        entry = json.loads(fmt.format(record))
        # Matches Pounce's _JSONFormatter envelope exactly.
        assert set(entry) == {"ts", "level", "logger", "message"}
        assert entry["level"] == "info"
        assert entry["logger"] == "chirp"
        assert entry["message"] == "plain message"

    def test_exception_record_carries_exception_field(self) -> None:
        fmt = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="chirp",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=exc_info,
        )
        entry = json.loads(fmt.format(record))
        assert "ValueError: boom" in entry["exception"]

    def test_non_serializable_extra_falls_back_without_raising(self) -> None:
        """A getMessage that raises must never crash format()."""
        fmt = JSONFormatter()

        class _Exploding:
            def __str__(self) -> str:
                raise RuntimeError("cannot stringify")

        record = logging.LogRecord(
            name="chirp",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="%s",
            args=(_Exploding(),),
            exc_info=None,
        )
        # Must not raise, and must still be parseable JSON.
        out = fmt.format(record)
        entry = json.loads(out)
        assert entry["logger"] == "chirp"


# ---------------------------------------------------------------------------
# configure_json_logging idempotence / scope
# ---------------------------------------------------------------------------


class TestConfigureJsonLogging:
    @pytest.fixture(autouse=True)
    def _restore_chirp_logger(self):
        logger = logging.getLogger("chirp")
        handlers = list(logger.handlers)
        propagate = logger.propagate
        level = logger.level
        yield
        logger.handlers[:] = handlers
        logger.propagate = propagate
        logger.setLevel(level)

    def test_installs_json_handler_on_chirp_logger_only(self) -> None:
        configure_json_logging()
        logger = logging.getLogger("chirp")
        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)]
        assert len(json_handlers) == 1
        assert logger.propagate is False
        # basicConfig is never called → root logger is untouched by us.

    def test_idempotent_no_handler_stacking(self) -> None:
        configure_json_logging()
        configure_json_logging()
        configure_json_logging()
        logger = logging.getLogger("chirp")
        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)]
        assert len(json_handlers) == 1

    def test_app_freeze_installs_when_log_format_json(self) -> None:
        app = App(config=AppConfig(log_format="json", secret_key="x" * 32))
        app.freeze()
        logger = logging.getLogger("chirp")
        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)]
        assert len(json_handlers) == 1

    def test_app_freeze_skips_when_log_format_not_json(self) -> None:
        app = App(config=AppConfig(log_format="auto", secret_key="x" * 32))
        app.freeze()
        logger = logging.getLogger("chirp")
        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)]
        assert json_handlers == []


# ---------------------------------------------------------------------------
# Acceptance — end-to-end through TestClient incl. Suspense drain
# ---------------------------------------------------------------------------


class TestIssue379Acceptance:
    @pytest.fixture(autouse=True)
    def _restore_chirp_logger(self):
        logger = logging.getLogger("chirp")
        handlers = list(logger.handlers)
        propagate = logger.propagate
        level = logger.level
        yield
        logger.handlers[:] = handlers
        logger.propagate = propagate
        logger.setLevel(level)

    @pytest.mark.issue(379)
    async def test_json_format_and_trace_context_through_request(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """log_format=json + an active OTel span → framework logs match the
        server JSON envelope AND carry trace_id/span_id, including from inside a
        Suspense deferred-block drain (which survives via copy_context).

        Asserts against the framework's *actual* installed handler output (the
        freeze-installed JSONFormatter, propagate=False) — not caplog, whose
        root handler is bypassed once configure_json_logging() stops
        propagation. We attach a capturing StreamHandler with the same
        JSONFormatter so we observe exactly the lines the framework emits.
        """
        import io

        _install_fake_otel(monkeypatch, valid=True)

        (tmp_path / "dash.html").write_text(
            "<html><body><h1>{{ title }}</h1>"
            '<div id="stats">{% block stats %}'
            "{% if stats is deferred %}<span>…</span>"
            "{% else %}<ul>{% for s in stats %}<li>{{ s }}</li>{% end %}</ul>{% end %}"
            "{% end %}</div></body></html>"
        )

        app = App(config=AppConfig(template_dir=tmp_path, log_format="json", secret_key="x" * 32))

        async def load_stats() -> list[str]:
            # Emitted from the deferred-block drain; copy_context keeps the span.
            structured_log(logging.INFO, "loading stats", path="/", method="GET")
            return ["alice", "bob"]

        @app.route("/")
        def index():
            from chirp.templating.returns import Suspense

            structured_log(logging.INFO, "handler entered", path="/", method="GET")
            return Suspense("dash.html", title="Dash", stats=load_stats())

        # freeze installs the JSONFormatter on the "chirp" logger.
        app.freeze()
        logger = logging.getLogger("chirp")
        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)]
        assert len(json_handlers) == 1, "freeze did not install the framework JSON formatter"

        # Observe the exact lines the framework emits through its own formatter.
        buf = io.StringIO()
        capture = logging.StreamHandler(buf)
        capture.setFormatter(JSONFormatter())
        capture.setLevel(logging.INFO)
        logger.addHandler(capture)
        prev_level = logger.level
        logger.setLevel(logging.INFO)  # default chirp logger level is WARNING
        try:
            async with TestClient(app) as client:
                response = await client.get("/")
        finally:
            logger.removeHandler(capture)
            logger.setLevel(prev_level)
        assert response.status == 200
        assert "<li>alice</li>" in response.text, "deferred block did not resolve"

        # Each emitted line is the server JSON envelope; the structured payload
        # (incl. trace_id/span_id) rides inside the "message" field.
        envelopes = [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]
        assert envelopes, "framework emitted no JSON log lines"
        for env in envelopes:
            assert set(env) == {"ts", "level", "logger", "message"}, env
            assert env["logger"] == "chirp"

        payloads = [json.loads(env["message"]) for env in envelopes]
        handler_payloads = [p for p in payloads if p.get("message") == "handler entered"]
        drain_payloads = [p for p in payloads if p.get("message") == "loading stats"]
        assert handler_payloads, f"no handler log in {payloads!r}"
        assert drain_payloads, f"no Suspense-drain log in {payloads!r}"

        # Buffered handler path carries trace context.
        assert handler_payloads[-1]["trace_id"] == _TRACE_ID_HEX
        assert handler_payloads[-1]["span_id"] == _SPAN_ID_HEX
        # Suspense drain path carries trace context (survives copy_context).
        assert drain_payloads[-1]["trace_id"] == _TRACE_ID_HEX
        assert drain_payloads[-1]["span_id"] == _SPAN_ID_HEX
