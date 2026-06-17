"""Tests for the ``signal()`` primitive.

Covers the registry (register / emit / coalesce semantics), derived recompute on
dependency change, the auto-registered ``/_chirp/live`` EventStream emitting
named events, SSR initial seeding through the template globals, free-threading
concurrency (concurrent emits under the Lock — root AGENTS.md Lock proof), and
the dead-binding contract check (the #238 dead-ticker class).
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

import pytest

from chirp import App
from chirp.config import AppConfig
from chirp.contracts.rules_signals import check_signal_bindings
from chirp.contracts.types import Severity
from chirp.realtime.signal_globals import make_signal_globals
from chirp.realtime.signal_stream import make_signal_stream
from chirp.realtime.signals import (
    _SCOPE_PREFIX,
    DerivedSpec,
    SignalRegistry,
    SignalSpec,
    validate_signal_name,
)
from chirp.testing import TestClient

# ---------------------------------------------------------------------------
# Spec + name validation
# ---------------------------------------------------------------------------


class TestSignalName:
    def test_valid_names(self) -> None:
        for name in ("balance", "net_worth", "a.b", "ns:topic", "x-1"):
            assert validate_signal_name(name) == name

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            validate_signal_name("")

    def test_rejects_illegal_chars(self) -> None:
        for bad in ("a b", "a/b", "a\nb", "a,b"):
            with pytest.raises(ValueError, match="invalid"):
                validate_signal_name(bad)


class TestSignalSpec:
    def test_render_defaults_to_str(self) -> None:
        spec = SignalSpec(name="x")
        assert spec.render_value(42) == "42"

    def test_render_uses_callable(self) -> None:
        spec = SignalSpec(name="x", render=lambda v: f"${v}")
        assert spec.render_value(5) == "$5"


# ---------------------------------------------------------------------------
# Registry: register / emit / cache
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_and_introspect(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", initial=lambda: 100))
        assert reg.has("balance")
        assert reg.names == frozenset({"balance"})
        assert not reg.empty

    def test_empty_when_nothing_registered(self) -> None:
        assert SignalRegistry().empty

    def test_duplicate_registration_rejected(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="x"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(SignalSpec(name="x"))

    def test_initial_seeds_value_cache(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", initial=lambda: 1234, render=lambda v: f"{v:,}"))
        assert reg.current_rendered("balance") == "1,234"

    def test_emit_updates_cache(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", initial=lambda: 0))
        reg.emit("balance", 99)
        assert reg.cached_value("balance") == 99
        assert reg.current_rendered("balance") == "99"

    def test_emit_unregistered_raises(self) -> None:
        with pytest.raises(KeyError, match="not registered"):
            SignalRegistry().emit("ghost", 1)

    def test_render_for_emit_isolates_failure(self) -> None:
        reg = SignalRegistry()

        def boom(_v: object) -> str:
            raise RuntimeError("render kaput")

        reg.register(SignalSpec(name="x", render=boom))
        # Render failure returns None (event skipped) rather than propagating.
        assert reg.render_for_emit("x", 1) is None

    def test_coalesce_flag_recorded(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="log", coalesce=False))
        spec = reg.spec("log")
        assert spec is not None
        assert spec.coalesce is False

    def test_session_scoped_emit_isolates_cache_and_bus(self) -> None:
        """Session-scoped signals fan out on aud-scoped bus topics (#315)."""
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", audience="session", initial=lambda: 0))
        reg.emit("balance", 10, audience_key="alice")
        reg.emit("balance", 20, audience_key="bob")
        assert reg.cached_value("balance", audience_key="alice") == 10
        assert reg.cached_value("balance", audience_key="bob") == 20
        assert reg.cached_value("balance", audience_key="") is None

    def test_session_scoped_emit_requires_audience_key(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", audience="session"))
        with pytest.raises(ValueError, match="audience_key"):
            reg.emit("balance", 1)


# ---------------------------------------------------------------------------
# Derived recompute on dependency change
# ---------------------------------------------------------------------------


class TestDerived:
    def test_derived_recomputes_on_dependency_emit(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", initial=lambda: 10))
        reg.register(SignalSpec(name="holdings", initial=lambda: 5))
        reg.register_derived(
            DerivedSpec(name="net_worth", deps=("balance", "holdings"), compute=lambda b, h: b + h)
        )
        # SSR seed computes from cached deps.
        assert reg.current_rendered("net_worth") == "15"
        reg.emit("balance", 100)
        assert reg.cached_value("net_worth") == 105

    def test_derived_emits_on_any_dependency(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="a", initial=lambda: 1))
        reg.register(SignalSpec(name="b", initial=lambda: 2))
        reg.register_derived(DerivedSpec(name="sum", deps=("a", "b"), compute=lambda a, b: a + b))
        reg.emit("b", 40)
        assert reg.cached_value("sum") == 41

    def test_derived_compute_failure_isolated(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="a", initial=lambda: 0))

        def boom(_a: object) -> int:
            raise RuntimeError("compute kaput")

        reg.register_derived(DerivedSpec(name="bad", deps=("a",), compute=boom))
        # Emitting the dependency must not raise despite a failing derived.
        reg.emit("a", 1)
        assert reg.cached_value("a") == 1

    async def test_dependency_emit_publishes_derived_on_bus(self) -> None:
        """A dependency emit must FAN OUT the derived's topic on the bus too.

        Recomputing the value cache is not enough: the derived has its own
        ``sse-swap`` bindings, so a ``ChangeEvent`` MUST be published on the
        derived's scope or the badge never updates on the wire — the headline
        bug. This asserts the re-emit, not just the recompute.
        """
        reg = SignalRegistry()
        reg.register(SignalSpec(name="notifications", initial=lambda: ()))
        reg.register_derived(
            DerivedSpec(
                name="notif_badge", deps=("notifications",), compute=lambda notes: len(notes)
            )
        )

        received: list[object] = []

        async def watch() -> None:
            async for event in reg.bus.subscribe(_SCOPE_PREFIX + "notif_badge"):
                received.append(event)
                return

        task = asyncio.create_task(watch())
        await asyncio.sleep(0.02)  # let the subscriber register on the bus
        reg.emit("notifications", ("x", "y"))
        await asyncio.wait_for(task, timeout=1.0)

        assert len(received) == 1  # the derived re-emitted on its own scope
        assert reg.cached_value("notif_badge") == 2

    async def test_source_generator_path_recomputes_and_reemits_derived(self) -> None:
        """The source-generator path (registry.emit from a pumped source) must
        recompute + re-emit the derived exactly like an imperative app.emit.

        This is the reported regression: the notifications SOURCE yields, the
        merge stream pumps it through ``registry.emit``, and the derived badge
        must appear on the wire as its own named event.
        """

        async def source():
            await asyncio.sleep(0.02)
            yield ("a", "b", "c")
            await asyncio.sleep(1.0)  # keep the stream open past collection

        reg = SignalRegistry()
        reg.register(
            SignalSpec(
                name="notifications",
                initial=lambda: (),
                source=source,
                render=lambda notes: "|".join(notes),
            )
        )
        reg.register_derived(
            DerivedSpec(
                name="notif_badge",
                deps=("notifications",),
                compute=lambda notes: len(notes),
                render=lambda n: f"count={n}",
            )
        )
        stream = make_signal_stream(reg, ("notifications", "notif_badge"))
        gen = stream.generator.__aiter__()
        seen: dict[str, str] = {}
        try:
            for _ in range(2):
                event = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
                seen[event.event] = event.data
        finally:
            await gen.aclose()
        # BOTH the source signal AND its derived must surface on the wire.
        assert seen.get("notifications") == "a|b|c"
        assert seen.get("notif_badge") == "count=3"

    def test_transitive_derived_cascade(self) -> None:
        """A derived of a derived must recompute when the ROOT dependency emits.

        ``DerivedSpec`` docs promise recompute "whenever ANY of its deps
        changes" — and a derived's value changing IS a change. The cascade must
        be transitive, or a multi-stage derived chain silently stalls.
        """
        reg = SignalRegistry()
        reg.register(SignalSpec(name="a", initial=lambda: 1))
        reg.register_derived(DerivedSpec(name="b", deps=("a",), compute=lambda a: a + 1))
        reg.register_derived(DerivedSpec(name="c", deps=("b",), compute=lambda b: b * 10))
        reg.emit("a", 5)
        assert reg.cached_value("b") == 6
        assert reg.cached_value("c") == 60

    def test_pure_derived_reads_only_input_value(self) -> None:
        """The pure-derived contract: a derived computes from the emitted VALUE.

        A signal value carries everything its deriveds need (here a payload with
        both a list and its count), so the derived is a pure function of that
        value — deterministic regardless of any process-local store. This is the
        Lucky Cat ``notif_badge`` shape (``feed.unread``, never a store re-read),
        and the contract that makes deriveds correct across workers.
        """
        from dataclasses import dataclass

        @dataclass(frozen=True, slots=True)
        class Feed:
            notes: tuple[str, ...]
            unread: int

        reg = SignalRegistry()
        reg.register(SignalSpec(name="notifications", initial=lambda: Feed((), 0)))
        reg.register_derived(
            DerivedSpec(
                name="notif_badge",
                deps=("notifications",),
                compute=lambda feed: feed.unread,  # PURE: reads only the input value
            )
        )
        reg.emit("notifications", Feed(("a", "b", "c"), 3))
        assert reg.cached_value("notif_badge") == 3
        # A later snapshot with the watermark advanced clears the badge purely.
        reg.emit("notifications", Feed(("a", "b", "c"), 0))
        assert reg.cached_value("notif_badge") == 0


# ---------------------------------------------------------------------------
# Emit dedup (#3): an unchanged value is idempotent — skip the redundant event
# ---------------------------------------------------------------------------


class TestEmitDedup:
    """A pure render maps equal values to equal payloads, so re-emitting an
    unchanged value would fan out a byte-identical swap. The registry skips it
    (and the derived cascade) unless the signal opts out with ``coalesce=False``."""

    async def _events_on(self, reg, scope, emits, *, gap=0.03):
        """Subscribe to *scope*, run each thunk in *emits* with a gap between (so the
        bus delivers each event before the next, isolating registry dedup from any
        bus-level coalescing), and return the events received on that scope."""
        received: list[object] = []

        async def watch() -> None:
            async for event in reg.bus.subscribe(scope):
                received.append(event)  # noqa: PERF401 - background collector, cancelled (no comprehension)

        task = asyncio.create_task(watch())
        await asyncio.sleep(0.02)
        for thunk in emits:
            thunk()
            await asyncio.sleep(gap)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return received

    async def test_repeat_value_is_deduped(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance"))
        events = await self._events_on(
            reg,
            _SCOPE_PREFIX + "balance",
            [lambda: reg.emit("balance", 5), lambda: reg.emit("balance", 5)],
        )
        assert len(events) == 1  # the identical second emit is skipped

    async def test_changed_value_emits_each_time(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance"))
        events = await self._events_on(
            reg,
            _SCOPE_PREFIX + "balance",
            [lambda: reg.emit("balance", 5), lambda: reg.emit("balance", 6)],
        )
        assert len(events) == 2

    async def test_coalesce_false_emits_repeats(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="log", coalesce=False))  # append/drop-sensitive
        events = await self._events_on(
            reg,
            _SCOPE_PREFIX + "log",
            [lambda: reg.emit("log", "x"), lambda: reg.emit("log", "x")],
        )
        assert len(events) == 2  # every emit fires, even a repeat value

    async def test_derived_unchanged_projection_is_deduped(self) -> None:
        # The source value CHANGES but the derived projection is identical → the
        # derived emits once (rank/project once, emit only on a real change).
        reg = SignalRegistry()
        reg.register(SignalSpec(name="src"))
        reg.register_derived(DerivedSpec(name="parity", deps=("src",), compute=lambda n: n % 2))
        events = await self._events_on(
            reg,
            _SCOPE_PREFIX + "parity",
            [lambda: reg.emit("src", 2), lambda: reg.emit("src", 4)],  # both even → parity 0
        )
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Free-threading: concurrent emits under the Lock (AGENTS.md Lock proof)
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_emits_are_lock_safe(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="counter", initial=lambda: 0))
        reg.register_derived(DerivedSpec(name="double", deps=("counter",), compute=lambda c: c * 2))

        n_threads = 16
        per_thread = 200
        barrier = threading.Barrier(n_threads)

        def worker(base: int) -> None:
            barrier.wait()
            for i in range(per_thread):
                reg.emit("counter", base * per_thread + i)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # The cache must hold a coherent (not torn) value, and the derived must
        # be a consistent double of *some* committed counter value — no crash,
        # no partial state, under contended Lock access.
        counter = reg.cached_value("counter")
        double = reg.cached_value("double")
        assert isinstance(counter, int)
        assert isinstance(double, int)
        # double is always exactly 2x a value that was committed at some point.
        assert double % 2 == 0


# ---------------------------------------------------------------------------
# Template globals: SSR seeding + connect wrapper
# ---------------------------------------------------------------------------


class TestGlobals:
    def test_signal_global_seeds_initial(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", initial=lambda: 1234, render=lambda v: f"{v:,}"))
        globals_ = make_signal_globals(reg)
        html = str(globals_["signal"]("balance"))
        assert 'sse-swap="balance"' in html
        assert 'hx-target="this"' in html
        assert "1,234" in html  # seeded, no flash

    def test_signal_global_no_seed_when_unset(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="ticker"))  # no initial
        globals_ = make_signal_globals(reg)
        html = str(globals_["signal"]("ticker"))
        assert 'sse-swap="ticker"' in html
        assert html.endswith("></span>")  # empty inner

    def test_signal_block_global_emits_div(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="card", initial=lambda: "<b>hi</b>"))
        globals_ = make_signal_globals(reg)
        html = str(globals_["signal_block"]("card"))
        assert html.startswith('<div sse-swap="card"')
        assert "<b>hi</b>" in html  # HTML fragment seed not escaped

    def test_signal_connect_subscribes_all(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="a", initial=lambda: 1))
        reg.register(SignalSpec(name="b", initial=lambda: 2))
        globals_ = make_signal_globals(reg)
        # Subscribe-all is the deliberate default: manual sse-swap sinks (e.g. the
        # bell badge) and composed-layout ordering make per-page ?topics= scoping
        # unsound, so the connect emits the bare stream URL (see signal_globals).
        str(globals_["signal"]("a"))
        connect = str(globals_["signal_connect"]())
        assert 'hx-ext="sse"' in connect
        assert 'sse-connect="/_chirp/live"' in connect
        assert "topics=" not in connect

    def test_signal_attrs_emits_bare_attrs_no_wrapper(self) -> None:
        """signal_attrs binds an EXISTING element: it emits only the attributes
        (sse-swap + hx-target), no <span>/<div> wrapper, so a layout's own grid
        container becomes a live sink without breaking its layout."""
        reg = SignalRegistry()
        reg.register(SignalSpec(name="board", initial=lambda: "x"))
        globals_ = make_signal_globals(reg)
        attrs = str(globals_["signal_attrs"]("board"))
        assert attrs == 'sse-swap="board" hx-target="this"'
        # No element is emitted (it decorates an existing tag).
        assert "<" not in attrs
        assert ">" not in attrs

    def test_signal_attrs_is_contract_detected(self) -> None:
        """A signal_attrs('x') call is recognised by the dead-binding contract by
        its call-site (like signal()/signal_block()), so the binding is validated
        even though the element's sse-swap is produced at render time."""
        # Bound + registered → no issue; bound + unregistered → dead-binding ERROR.
        ok = check_signal_bindings(
            {"page.html": "{{ signal_connect() }}<section {{ signal_attrs('board') }}>"},
            frozenset({"board"}),
        )
        assert not [i for i in ok if i.severity is Severity.ERROR]
        dead = check_signal_bindings(
            {"page.html": "{{ signal_connect() }}<section {{ signal_attrs('typo') }}>"},
            frozenset({"board"}),
        )
        assert any(i.category == "signal_dead_binding" for i in dead)


# ---------------------------------------------------------------------------
# /_chirp/live route: EventStream emitting named events
# ---------------------------------------------------------------------------


class TestLiveStream:
    async def test_stream_emits_named_event_on_emit(self) -> None:
        reg = SignalRegistry()
        reg.register(SignalSpec(name="balance", initial=lambda: 0))
        stream = make_signal_stream(reg, ("balance",))
        gen = stream.generator.__aiter__()

        # Give the subscriber task a tick to register, then emit.
        async def _emit_later() -> None:
            await asyncio.sleep(0.02)
            reg.emit("balance", 777)

        task = asyncio.create_task(_emit_later())
        event = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        await task
        assert event.event == "balance"
        assert event.data == "777"
        await gen.aclose()

    async def test_stream_from_async_source(self) -> None:
        reg = SignalRegistry()

        async def source():
            yield 1
            yield 2
            await asyncio.sleep(1.0)  # keep stream open past collection

        reg.register(SignalSpec(name="ticks", source=source))
        stream = make_signal_stream(reg, ("ticks",))
        gen = stream.generator.__aiter__()
        first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        assert first.event == "ticks"
        assert first.data in {"1", "2"}
        await gen.aclose()

    async def test_app_autoregisters_live_route(self) -> None:
        app = App(config=AppConfig())

        @app.signal("balance", initial=lambda: 5)
        async def balance():  # pragma: no cover - source not pumped in this test
            if False:
                yield 0

        app.freeze()
        paths = {r.path for r in app._runtime_state.router.routes}
        assert "/_chirp/live" in paths

    async def test_no_live_route_without_signals(self) -> None:
        app = App(config=AppConfig())

        @app.route("/")
        def home():
            from chirp.templating.returns import InlineTemplate

            return InlineTemplate("<p>hi</p>")

        app.freeze()
        paths = {r.path for r in app._runtime_state.router.routes}
        assert "/_chirp/live" not in paths

    async def test_live_route_end_to_end(self) -> None:
        app = App(config=AppConfig())

        @app.signal("balance", initial=lambda: 0)
        async def balance():
            for amount in (10, 20, 30):
                yield amount
            await asyncio.sleep(1.0)

        app.freeze()
        async with TestClient(app) as client:
            result = await client.sse("/_chirp/live?topics=balance", max_events=3)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        events = [e for e in result.events if e.event == "balance"]
        assert events, f"no balance events in {result.events!r}"
        assert {e.data for e in events} <= {"10", "20", "30"}


# ---------------------------------------------------------------------------
# App method wiring
# ---------------------------------------------------------------------------


class TestAppWiring:
    def test_emit_before_registration_raises(self) -> None:
        app = App(config=AppConfig())
        with pytest.raises(KeyError, match="not registered"):
            app.emit("ghost", 1)

    def test_imperative_emit_updates_cache(self) -> None:
        app = App(config=AppConfig())

        @app.signal("balance", initial=lambda: 0)
        async def balance():  # pragma: no cover
            if False:
                yield 0

        app.emit("balance", 42)
        assert app._mutable_state.signal_registry.cached_value("balance") == 42

    def test_derived_method_registers(self) -> None:
        app = App(config=AppConfig())

        @app.signal("a", initial=lambda: 1)
        async def a():  # pragma: no cover
            if False:
                yield 0

        @app.derived("doubled", on=("a",))
        def doubled(a_val):
            return a_val * 2

        reg = app._mutable_state.signal_registry
        assert "doubled" in reg.names
        reg.emit("a", 5)
        assert reg.cached_value("doubled") == 10

    def test_signal_globals_registered_at_freeze(self) -> None:
        app = App(config=AppConfig())

        @app.signal("x", initial=lambda: 1)
        async def x():  # pragma: no cover
            if False:
                yield 0

        app.freeze()
        for name in ("signal", "signal_block", "signal_connect"):
            assert name in app._mutable_state.template_globals


# ---------------------------------------------------------------------------
# Contract check: dead binding (#238 dead-ticker class)
# ---------------------------------------------------------------------------


class TestDeadBindingCheck:
    def test_dead_binding_is_error_issue_238(self) -> None:
        """A signal binding with no producer is an ERROR (#238 dead-ticker class)."""
        sources = {
            "page.html": (
                '<div hx-ext="sse" sse-connect="/_chirp/live" hx-disinherit="hx-target hx-swap">'
                '<span sse-swap="balance" hx-target="this">0</span>'
                "</div>"
            )
        }
        issues = check_signal_bindings(sources, frozenset())  # no producers
        # No registry => SSE crossref owns the case; this rule stays silent.
        assert issues == []

        # With other signals registered but not 'balance', it's a dead binding.
        issues = check_signal_bindings(sources, frozenset({"ticker"}))
        dead = [i for i in issues if i.category == "signal_dead_binding"]
        assert len(dead) == 1
        assert dead[0].severity is Severity.ERROR
        assert "balance" in dead[0].message

    def test_registered_binding_passes(self) -> None:
        sources = {
            "page.html": (
                '<div hx-ext="sse" sse-connect="/_chirp/live">'
                '<span sse-swap="balance" hx-target="this">0</span>'
                "</div>"
            )
        }
        issues = check_signal_bindings(sources, frozenset({"balance"}))
        assert not [i for i in issues if i.category == "signal_dead_binding"]

    def test_signal_connect_global_recognized(self) -> None:
        sources = {
            "page.html": (
                '{{ signal_connect() }}<span sse-swap="balance" hx-target="this">0</span></div>'
            )
        }
        issues = check_signal_bindings(sources, frozenset({"other"}))
        dead = [i for i in issues if i.category == "signal_dead_binding"]
        assert len(dead) == 1
        assert "balance" in dead[0].message

    def test_orphan_producer_is_info(self) -> None:
        sources = {"page.html": "<p>no bindings here</p>"}
        issues = check_signal_bindings(sources, frozenset({"balance"}))
        orphans = [i for i in issues if i.category == "signal_orphan"]
        assert len(orphans) == 1
        assert orphans[0].severity is Severity.INFO

    @pytest.mark.issue(316)
    def test_composed_page_raw_sse_swap_dead_binding(self) -> None:
        """Hand-written sse-swap on a page under signal_connect() is validated (#316)."""
        sources = {
            "_layout.html": "{{ signal_connect() }}<div>{% block content %}{% endblock %}</div>",
            "page.html": '<span sse-swap="typo" hx-target="this">0</span>',
        }
        issues = check_signal_bindings(sources, frozenset({"balance"}))
        dead = [i for i in issues if i.category == "signal_dead_binding"]
        assert len(dead) == 1
        assert "typo" in dead[0].message

    def test_composed_page_raw_sse_swap_nudge(self) -> None:
        sources = {
            "_layout.html": "{{ signal_connect() }}",
            "page.html": '<span sse-swap="balance" hx-target="this">0</span>',
        }
        issues = check_signal_bindings(sources, frozenset({"balance"}))
        nudges = [i for i in issues if i.category == "signal_raw_sse_swap"]
        assert len(nudges) == 1
        assert "signal_attrs" in nudges[0].message

    @pytest.mark.issue(316)
    def test_competing_sse_scope_not_signal_binding(self) -> None:
        """A page with its own sse_scope stream must not false-positive (#316)."""
        sources = {
            "_layout.html": "{{ signal_connect() }}",
            "detail.html": (
                '{% from "chirp/sse.html" import sse_scope %}{{ sse_scope("/markets/BTC/stream") }}'
            ),
        }
        issues = check_signal_bindings(sources, frozenset({"balance"}))
        assert not [i for i in issues if i.category == "signal_dead_binding"]
        assert not [i for i in issues if i.category == "signal_raw_sse_swap"]
