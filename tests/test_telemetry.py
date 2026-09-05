"""Tests for best-effort OpenTelemetry spans (#427, #428)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

pytest.importorskip("httpx")

from chirp.ai.llm import LLM
from chirp.telemetry import trace_span
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import compile_tools


class _RecordedSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attributes: dict[str, Any] = {}
        self.exceptions: list[BaseException] = []
        self.status: Any = None
        self.ended = False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_exception(self, exc: BaseException) -> None:
        self.exceptions.append(exc)

    def set_status(self, status: Any) -> None:
        self.status = status

    def end(self) -> None:
        self.ended = True


class _SpanToken:
    def __init__(self, span: _RecordedSpan) -> None:
        self._span = span

    def __enter__(self) -> _RecordedSpan:
        return self._span

    def __exit__(self, *args: object) -> bool:
        return False


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_RecordedSpan] = []

    def start_span(self, name: str) -> _RecordedSpan:
        span = _RecordedSpan(name)
        self.spans.append(span)
        return span


def _install_recording_otel(monkeypatch: pytest.MonkeyPatch) -> _FakeTracer:
    tracer = _FakeTracer()

    trace_mod = types.ModuleType("opentelemetry.trace")

    class _Status:
        def __init__(self, code: Any, description: str = "") -> None:
            self.code = code
            self.description = description

    class _StatusCode:
        ERROR = "ERROR"

    trace_mod.Status = _Status  # type: ignore[attr-defined]
    trace_mod.StatusCode = _StatusCode  # type: ignore[attr-defined]
    trace_mod.use_span = lambda span, end_on_exit=True: _SpanToken(span)  # type: ignore[attr-defined]

    otel_trace = types.ModuleType("opentelemetry.trace")
    otel_trace.get_tracer = lambda name: tracer  # type: ignore[attr-defined]
    otel_trace.use_span = trace_mod.use_span  # type: ignore[attr-defined]
    otel_trace.Status = _Status  # type: ignore[attr-defined]
    otel_trace.StatusCode = _StatusCode  # type: ignore[attr-defined]

    otel_pkg = types.ModuleType("opentelemetry")
    otel_pkg.trace = otel_trace  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "opentelemetry", otel_pkg)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", otel_trace)
    return tracer


class TestTraceSpan:
    def test_no_op_when_otel_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "opentelemetry", None)
        with trace_span("demo.span", foo="bar") as span:
            assert span is None

    def test_records_attributes_and_duration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tracer = _install_recording_otel(monkeypatch)
        with trace_span("demo.span", provider="openai", model="gpt-4o"):
            pass
        assert len(tracer.spans) == 1
        span = tracer.spans[0]
        assert span.name == "demo.span"
        assert span.attributes["provider"] == "openai"
        assert span.attributes["model"] == "gpt-4o"
        assert "duration_ms" in span.attributes
        assert span.ended is True

    def test_records_error_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tracer = _install_recording_otel(monkeypatch)
        with pytest.raises(RuntimeError, match="boom"), trace_span("demo.fail"):
            raise RuntimeError("boom")
        span = tracer.spans[0]
        assert span.status is not None
        assert span.status.code == "ERROR"
        assert span.exceptions


class TestLLMSpans:
    @pytest.mark.asyncio
    async def test_generate_emits_llm_generate_span(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        tracer = _install_recording_otel(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )

        transport = httpx.MockTransport(handler)
        real_init = httpx.AsyncClient.__init__

        def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)

        llm = LLM("openai:gpt-4o", api_key="sk-test")
        text = await llm.generate("Hello")
        assert text == "ok"
        assert any(s.name == "llm.generate" for s in tracer.spans)
        span = next(s for s in tracer.spans if s.name == "llm.generate")
        assert span.attributes["provider"] == "openai"
        assert span.attributes["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_stream_emits_llm_stream_span(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        tracer = _install_recording_otel(monkeypatch)

        body = "\n".join(
            [
                'data: {"choices": [{"delta": {"content": "A"}}]}',
                'data: {"choices": [{"delta": {"content": "B"}}]}',
                "data: [DONE]",
            ]
        ).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        transport = httpx.MockTransport(handler)
        real_init = httpx.AsyncClient.__init__

        def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)

        llm = LLM("openai:gpt-4o", api_key="sk-test")
        tokens = [token async for token in llm.stream("Hi")]
        assert tokens == ["A", "B"]
        span = next(s for s in tracer.spans if s.name == "llm.stream")
        assert span.attributes["tokens_out"] == 2


class TestToolCallSpans:
    @pytest.mark.asyncio
    async def test_sync_tool_emits_tool_call_span(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tracer = _install_recording_otel(monkeypatch)

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        registry = compile_tools([("greet", "Greet someone", greet)], ToolEventBus())
        result = await registry.call_tool("greet", {"name": "World"})
        assert result == "Hello, World!"
        span = next(s for s in tracer.spans if s.name == "tool.call")
        assert span.attributes["tool_name"] == "greet"

    @pytest.mark.asyncio
    async def test_async_tool_emits_tool_call_span(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tracer = _install_recording_otel(monkeypatch)

        async def search(query: str) -> list[str]:
            return [query]

        registry = compile_tools([("search", "Search", search)], ToolEventBus())
        result = await registry.call_tool("search", {"query": "chirp"})
        assert result == ["chirp"]
        assert any(s.name == "tool.call" for s in tracer.spans)

    @pytest.mark.asyncio
    async def test_tool_error_recorded_on_span(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tracer = _install_recording_otel(monkeypatch)

        def boom() -> None:
            raise ValueError("tool failed")

        registry = compile_tools([("boom", "Boom", boom)], ToolEventBus())
        with pytest.raises(ValueError, match="tool failed"):
            await registry.call_tool("boom", {})
        span = next(s for s in tracer.spans if s.name == "tool.call")
        assert span.attributes["error"] == "ValueError"
        assert span.status is not None


@pytest.mark.issue(427)
class TestIssue427Acceptance:
    @pytest.mark.asyncio
    async def test_llm_spans_no_op_without_otel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        monkeypatch.setitem(sys.modules, "opentelemetry", None)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )

        transport = httpx.MockTransport(handler)
        real_init = httpx.AsyncClient.__init__

        def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)

        llm = LLM("openai:gpt-4o", api_key="sk-test")
        assert await llm.generate("x") == "ok"


@pytest.mark.issue(428)
class TestIssue428Acceptance:
    @pytest.mark.asyncio
    async def test_tool_call_span_and_event_bus_both_fire(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio

        tracer = _install_recording_otel(monkeypatch)
        bus = ToolEventBus()

        async def collect_one() -> Any:
            async for event in bus.subscribe():
                return event
            return None

        def add(x: int, y: int) -> int:
            return x + y

        registry = compile_tools([("add", "Add numbers", add)], bus)
        collector = asyncio.create_task(collect_one())
        await asyncio.sleep(0)  # let the subscriber register before emit
        assert await registry.call_tool("add", {"x": 2, "y": 3}) == 5
        event = await asyncio.wait_for(collector, timeout=1.0)
        assert event.tool_name == "add"
        assert any(s.name == "tool.call" for s in tracer.spans)


@pytest.mark.issue(1063)
@pytest.mark.parametrize("otel_enabled", [False, True])
@pytest.mark.parametrize("async_handler", [False, True])
@pytest.mark.parametrize("error_kind", ["unauthorized", "forbidden", "unexpected", "cancelled"])
async def test_traced_tool_preserves_exception_identity(
    monkeypatch: pytest.MonkeyPatch, otel_enabled: bool, async_handler: bool, error_kind: str
) -> None:
    import asyncio
    from dataclasses import FrozenInstanceError

    from chirp.errors import HTTPError

    tracer = _install_recording_otel(monkeypatch) if otel_enabled else None
    if not otel_enabled:
        monkeypatch.setitem(sys.modules, "opentelemetry", None)
    error = {
        "unauthorized": HTTPError(401, "Unauthorized"),
        "forbidden": HTTPError(403, "Forbidden"),
        "unexpected": RuntimeError("internal-secret"),
        "cancelled": asyncio.CancelledError(),
    }[error_kind]

    def gate() -> None:
        raise error

    async def async_gate() -> None:
        await asyncio.sleep(0)
        gate()

    registry = compile_tools(
        [("gate", "Authorization gate", async_gate if async_handler else gate)], ToolEventBus()
    )
    with pytest.raises(type(error)) as caught:
        await registry.call_tool("gate", {})
    assert caught.value is error
    frames = []
    traceback = error.__traceback__
    while traceback is not None:
        frames.append(traceback.tb_frame.f_code.co_name)
        traceback = traceback.tb_next
    assert "gate" in frames
    assert "__exit__" not in frames
    if isinstance(error, HTTPError):
        with pytest.raises(FrozenInstanceError):
            error.detail = "changed"
    if tracer is not None:
        span = tracer.spans[0]
        assert span.exceptions == [error]
        assert span.attributes["error"] == type(error).__name__
        assert span.status.code == "ERROR"
        assert span.ended
