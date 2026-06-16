"""Chirp ``signal()`` — the declare-once / bind-many live-value primitive.

A *signal* is a server-owned named value, declared once, that fans out over a
single shared SSE connection to **every** template binding that listens for it.
``{{ signal('balance') }}`` in the topbar and ``{{ signal('balance') }}`` in a
modal both swap together from one ``event: balance`` on the wire — a cardinality
plain OOB cannot express (htmx's ``sse-swap`` matches with ``querySelectorAll``).

This module is the framework substrate behind the public ``@app.signal`` /
``@app.derived`` / ``app.emit`` surface and the ``signal()`` / ``signal_block()``
/ ``signal_connect()`` template globals. It is intentionally a *thin* layer over
existing transport:

- :class:`~chirp.realtime.events.SSEEvent` already emits named ``event:`` lines —
  the exact wire format htmx ``sse-swap="<name>"`` matches.
- :class:`~chirp.pages.reactive.bus.ReactiveBus` provides the free-threaded
  (``threading.Lock`` + per-subscriber ``asyncio.Queue`` + ``call_soon_threadsafe``
  + bounded back-pressure) fan-out. Here the bus *scope* is the signal name.

Free-threading (3.14t): :class:`SignalSpec` / :class:`DerivedSpec` are
``frozen``/``slots``; the registry's mutable maps + value cache are guarded by a
single ``threading.Lock`` (mirroring ``OOBRegistry``). Cross-thread emits ride
the bus's ``call_soon_threadsafe`` delivery path, so a sync-mode producer can
``app.emit(...)`` safely.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from chirp.pages.reactive.bus import ReactiveBus
from chirp.pages.reactive.events import ChangeEvent

logger = logging.getLogger("chirp.signals")

#: Allowed characters in a signal name. Matches the ``sse-swap`` attribute and
#: existing reactive scope keys, and is a subset of what :class:`SSEEvent`
#: already permits (no CR/LF/NUL). Validated at registration time, not at emit.
_SIGNAL_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")

#: Bus scope prefix so signal fan-out never collides with reactive-document
#: scopes sharing the same ``ReactiveBus`` family of keys.
_SCOPE_PREFIX = "signal:"


def validate_signal_name(name: str) -> str:
    """Return *name* if it is a legal signal name, else raise ``ValueError``.

    A signal name must be a non-empty string matching ``[A-Za-z0-9_.:-]+`` so it
    is safe as both an htmx ``sse-swap`` attribute value and an SSE ``event:``
    field. Rejection happens at registration, not at emit.
    """
    if not isinstance(name, str) or not name:
        msg = "signal name must be a non-empty string"
        raise ValueError(msg)
    if _SIGNAL_NAME_RE.match(name) is None:
        msg = (
            f"signal name {name!r} is invalid; allowed characters are "
            "letters, digits, and the set [_.:-] (to match sse-swap / SSE event names)"
        )
        raise ValueError(msg)
    return name


@dataclass(frozen=True, slots=True)
class SignalSpec:
    """Declaration of one signal — one producer, many bindings.

    Attributes:
        name: The signal name. Doubles as the SSE ``event:`` field and the
            htmx ``sse-swap`` attribute value bound in templates.
        source: Optional async generator factory yielding successive values.
            ``None`` for push-only signals driven by :meth:`App.emit`.
        initial: Optional zero-arg callable returning the SSR seed value, so a
            binding paints its current value with no empty-then-fill flash.
        render: Optional ``value -> str`` renderer. Defaults to ``str``; the
            result is the SSE ``data:`` payload and the SSR seed text.
        coalesce: Latest-wins (default). A live value is idempotent, so dropping
            a stale update under back-pressure is safe — the next emit reconciles
            every binding. Set ``False`` for append-style / drop-sensitive topics.
    """

    name: str
    source: Callable[[], AsyncIterator[Any]] | None = None
    initial: Callable[[], Any] | None = None
    render: Callable[[Any], str] | None = None
    coalesce: bool = True

    def render_value(self, value: Any) -> str:
        """Render *value* to its SSE/SSR string payload."""
        if self.render is not None:
            return self.render(value)
        return str(value)


@dataclass(frozen=True, slots=True)
class DerivedSpec:
    """Declaration of a derived signal — recomputed from other signals.

    A derived signal recomputes and re-emits whenever **any** of its ``deps``
    changes. ``compute`` receives the current values of ``deps`` (positionally,
    in declaration order) and returns the derived value.

    Attributes:
        name: The derived signal name (also a bindable ``sse-swap`` target).
        deps: Dependency signal names. A change to any of them triggers recompute.
        compute: ``(*dep_values) -> derived_value``.
        render: Optional ``value -> str`` renderer for the derived value.
    """

    name: str
    deps: tuple[str, ...]
    compute: Callable[..., Any]
    render: Callable[[Any], str] | None = None

    def render_value(self, value: Any) -> str:
        """Render *value* to its SSE/SSR string payload."""
        if self.render is not None:
            return self.render(value)
        return str(value)


@dataclass(slots=True)
class SignalRegistry:
    """Free-thread-safe registry of signals + derived signals.

    Holds the spec maps, a current-value cache (for SSR seeding and derived
    recompute), and a :class:`ReactiveBus` for fan-out keyed by signal name.
    All mutable state is guarded by a single ``threading.Lock``.
    """

    _specs: dict[str, SignalSpec] = field(default_factory=dict)
    _derived: dict[str, DerivedSpec] = field(default_factory=dict)
    #: signal name -> dependent derived names (reverse index for recompute).
    _dependents: dict[str, set[str]] = field(default_factory=dict)
    #: signal/derived name -> last rendered string value (SSR + derived inputs).
    _values: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    bus: ReactiveBus = field(default_factory=ReactiveBus)

    # -- registration (setup-only; called under App._check_not_frozen) --

    def register(self, spec: SignalSpec) -> None:
        """Register a primary signal. Raises on duplicate name (one producer)."""
        validate_signal_name(spec.name)
        with self._lock:
            if spec.name in self._specs or spec.name in self._derived:
                msg = (
                    f"signal {spec.name!r} is already registered; each signal has "
                    "exactly one producer (many bindings are the point)"
                )
                raise ValueError(msg)
            self._specs[spec.name] = spec
            if spec.initial is not None:
                # Seed lazily-evaluated initial into the value cache.
                try:
                    self._values[spec.name] = spec.initial()
                except Exception:
                    logger.exception("signal %r initial() failed during registration", spec.name)

    def register_derived(self, spec: DerivedSpec) -> None:
        """Register a derived signal that recomputes on any dependency change."""
        validate_signal_name(spec.name)
        for dep in spec.deps:
            validate_signal_name(dep)
        with self._lock:
            if spec.name in self._specs or spec.name in self._derived:
                msg = f"signal {spec.name!r} is already registered"
                raise ValueError(msg)
            self._derived[spec.name] = spec
            for dep in spec.deps:
                self._dependents.setdefault(dep, set()).add(spec.name)

    # -- introspection --

    def has(self, name: str) -> bool:
        """Whether *name* is a registered signal or derived signal."""
        with self._lock:
            return name in self._specs or name in self._derived

    @property
    def names(self) -> frozenset[str]:
        """Every registered signal + derived name (the producer set)."""
        with self._lock:
            return frozenset(self._specs) | frozenset(self._derived)

    @property
    def empty(self) -> bool:
        """Whether no signals (primary or derived) are registered."""
        with self._lock:
            return not self._specs and not self._derived

    def spec(self, name: str) -> SignalSpec | None:
        with self._lock:
            return self._specs.get(name)

    def source_specs(self) -> tuple[SignalSpec, ...]:
        """Primary signals that have an async ``source`` generator."""
        with self._lock:
            return tuple(s for s in self._specs.values() if s.source is not None)

    # -- value cache / SSR seed --

    def current_rendered(self, name: str) -> str | None:
        """Return the SSR-seed string for *name*, or ``None`` if unseeded.

        Reads the value cache (populated by ``initial()`` at registration and by
        every :meth:`emit`). A primary signal renders via its ``render``; a
        derived signal computes from its deps' cached values if not yet cached.
        """
        with self._lock:
            spec = self._specs.get(name)
            if spec is not None:
                if name not in self._values:
                    return None
                value = self._values[name]
                renderer = spec
            else:
                dspec = self._derived.get(name)
                if dspec is None:
                    return None
                if name in self._values:
                    value = self._values[name]
                else:
                    dep_values = [self._values.get(d) for d in dspec.deps]
                    if any(v is None for v in dep_values):
                        return None
                    try:
                        value = dspec.compute(*dep_values)
                    except Exception:
                        logger.exception("derived signal %r compute() failed for SSR seed", name)
                        return None
                renderer = dspec
        try:
            return renderer.render_value(value)
        except Exception:
            logger.exception("signal %r render failed for SSR seed", name)
            return None

    # -- emit / fan-out --

    def emit(self, name: str, value: Any) -> None:
        """Publish a new *value* for signal *name* and cascade to derived signals.

        Updates the value cache, fans out an ``event: <name>`` to every binding
        via the bus, then recomputes + re-emits **every** derived signal reachable
        from *name* — transitively, so a derived-of-a-derived also fires. Each
        recompute is published on the derived's own scope (its ``sse-swap``
        bindings), so a dependency change ALWAYS surfaces its deriveds on the
        wire, via both an imperative :meth:`emit` and the source-generator pump
        (which routes through this method). Safe to call from any thread (the bus
        hands cross-thread delivery to the subscriber's event loop).
        """
        with self._lock:
            if name not in self._specs and name not in self._derived:
                msg = (
                    f"signal {name!r} is not registered; declare it with "
                    "@app.signal or @app.derived before emitting"
                )
                raise KeyError(msg)
            spec = self._specs.get(name)
            prev_present = name in self._values
            prev = self._values.get(name)
            self._values[name] = value

        # Idempotent dedup: a coalescing signal whose value is unchanged would
        # fan out a byte-identical payload (a pure render maps equal values to
        # equal payloads) — skip the wire event AND the derived cascade entirely;
        # every binding already shows it. ``coalesce=False`` (append-/drop-
        # sensitive topics, e.g. a toast log) always emits, even on a repeat value.
        coalesce = spec.coalesce if spec is not None else True
        if coalesce and prev_present and _values_equal(prev, value):
            return

        self._publish(name, value)
        self._cascade(name)

    def _cascade(self, changed: str) -> None:
        """Recompute + re-emit every derived reachable from *changed*.

        A breadth-first walk of the reverse dependency index: each derived whose
        deps are all cached recomputes from those cached values, caches its new
        value, publishes it on its own scope, then enqueues ITS dependents — so a
        multi-stage derived chain (a derived of a derived) fully propagates from a
        single source emit. A ``visited`` guard bounds the walk and tolerates a
        cyclic registration (each derived recomputes at most once per emit). Each
        recompute is a pure function of the derived's INPUT SIGNAL VALUES — never
        external state — so the cascade is deterministic across workers.
        """
        visited: set[str] = set()
        frontier = [changed]
        while frontier:
            source = frontier.pop(0)
            with self._lock:
                dependents = sorted(self._dependents.get(source, ()))
                # Snapshot each dependent's spec + current dep values under the lock.
                pending = {
                    dname: (
                        self._derived[dname],
                        [self._values.get(d) for d in self._derived[dname].deps],
                    )
                    for dname in dependents
                    if dname in self._derived and dname not in visited
                }
            for dname, (dspec, dep_values) in pending.items():
                visited.add(dname)
                if any(v is None for v in dep_values):
                    continue
                try:
                    derived_value = dspec.compute(*dep_values)
                except Exception:
                    logger.exception(
                        "derived signal %r compute() failed on emit of %r", dname, source
                    )
                    continue
                with self._lock:
                    prev_present = dname in self._values
                    prev = self._values.get(dname)
                    self._values[dname] = derived_value
                # A derived is a PURE projection of its inputs, so an unchanged
                # value means an unchanged DOM — skip its wire event AND stop
                # propagating down this branch (its own dependents cannot have
                # changed either). The redundant-cascade fix (rank/project once,
                # emit only on real change).
                if prev_present and _values_equal(prev, derived_value):
                    continue
                self._publish(dname, derived_value)
                # Propagate transitively: this derived's value just changed, so
                # any derived listening on IT must recompute in the same cascade.
                frontier.append(dname)

    def _publish(self, name: str, value: Any) -> None:
        """Render *value* and fan it out as a ``ChangeEvent`` on the bus.

        Render errors are isolated here so one bad signal never poisons the
        shared connection: the value is cached, but no event is fanned out.
        """
        scope = _SCOPE_PREFIX + name
        # ChangeEvent carries the rendered payload in ``changed_paths`` so the
        # /_chirp/live merge generator can recover it without re-rendering
        # (keeping per-event work off the shared stream's hot path).
        self.bus.emit_sync(
            ChangeEvent(scope=scope, changed_paths=frozenset({_rendered_marker(name)}))
        )

    def render_for_emit(self, name: str, value: Any) -> str | None:
        """Render *value* for the wire, isolating render failure. ``None`` skips."""
        with self._lock:
            spec = self._specs.get(name)
            dspec = None if spec is not None else self._derived.get(name)
        renderer: SignalSpec | DerivedSpec | None = spec or dspec
        if renderer is None:
            return None
        try:
            return renderer.render_value(value)
        except Exception:
            logger.exception("signal %r render failed on emit", name)
            return None

    def cached_value(self, name: str) -> Any:
        """Return the cached raw value for *name* (``None`` if unset)."""
        with self._lock:
            return self._values.get(name)


def _rendered_marker(name: str) -> str:
    """Marker path stored in a ChangeEvent for signal *name*."""
    return f"signal::{name}"


def _values_equal(a: Any, b: Any) -> bool:
    """Whether two cached signal values are equal for emit dedup.

    A pure ``render`` maps equal values to equal payloads, so skipping the re-emit
    of an unchanged value never drops a real DOM change. Returns ``False`` on any
    comparison error (e.g. a value whose ``__eq__`` raises or is ambiguous), so the
    safe default is always "treat as changed → emit".
    """
    if a is b:
        return True
    try:
        return bool(a == b)
    except Exception:
        return False
