"""Chirp ``signal()`` — the declare-once / bind-many live-value primitive.

A *signal* is a server-owned named value, declared once, that fans out over a
single shared SSE connection to **every** template binding that listens for it.
``{{ signal('balance') }}`` in the topbar and ``{{ signal('balance') }}`` in a
modal both swap together from one update on the wire — a cardinality plain OOB
cannot express. Htmx 2 uses a named event; htmx 4 uses one targeted partial whose
``data-chirp-signal`` selector matches every sink.

This module is the framework substrate behind the public ``@app.signal`` /
``@app.derived`` / ``app.emit`` surface and the ``signal()`` / ``signal_block()``
/ ``signal_connect()`` template globals. It is intentionally a *thin* layer over
existing transport:

- The private signal update remains client-neutral until the SSE response
  boundary chooses the frozen htmx 2 or htmx 4 dialect.
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
import secrets
import threading
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from chirp.pages.reactive.bus import ReactiveBus
from chirp.pages.reactive.events import ChangeEvent
from chirp.realtime.events import _SignalUpdate
from chirp.realtime.signal_backplane import (
    _SignalBackplaneCoordinator,
    _SignalBackplaneDescriptor,
    _SignalBackplaneError,
    _SignalBackplanePlan,
    signal_subject,
)

SignalAudience = Literal["global", "session"]

logger = logging.getLogger("chirp.signals")

#: Allowed characters in a signal name. Matches the ``sse-swap`` attribute and
#: existing reactive scope keys, and is a subset of what :class:`SSEEvent`
#: already permits (no CR/LF/NUL). Validated at registration time, not at emit.
_SIGNAL_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")

#: Bus scope prefix so signal fan-out never collides with reactive-document
#: scopes sharing the same ``ReactiveBus`` family of keys.
_SCOPE_PREFIX = "signal:"

# Process-private key keeps session identifiers out of ReactiveBus scopes and
# therefore out of its bounded-drop diagnostics. Memory subjects need only be
# stable inside this process; Redis subjects use AppConfig.secret_key instead.
_MEMORY_SUBJECT_KEY = secrets.token_bytes(32)


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
        audience: ``"global"`` (default) fans to every connection; ``"session"``
            fans only to connections whose trusted server-side session audience
            matches the emit ``audience_key`` (per-visitor state — balance,
            notifications). The key is never placed in the browser URL.
    """

    name: str
    source: Callable[[], AsyncIterator[Any]] | None = None
    initial: Callable[[], Any] | None = None
    render: Callable[[Any], str] | None = None
    coalesce: bool = True
    audience: SignalAudience = "global"

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
        audience: Inherited from dependencies — session when any dep is session-
            scoped; otherwise global. Set automatically at registration.
    """

    name: str
    deps: tuple[str, ...]
    compute: Callable[..., Any]
    render: Callable[[Any], str] | None = None
    audience: SignalAudience = "global"

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
    #: (audience_key, name) -> last value. ``audience_key`` is ``""`` for global.
    _values: dict[tuple[str, str], Any] = field(default_factory=dict, repr=False)
    #: Emitter-rendered payloads used by the memory stream without re-rendering.
    _rendered_values: dict[tuple[str, str], str] = field(default_factory=dict, repr=False)
    #: Longest-prefix URL map for proactive topic activation (#317).
    _prefix_topics: dict[str, frozenset[str]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    bus: ReactiveBus = field(default_factory=ReactiveBus)
    _backplane: _SignalBackplaneCoordinator | None = field(default=None, init=False, repr=False)
    _backplane_bound: bool = field(default=False, init=False, repr=False)

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
            if spec.initial is not None and spec.audience == "global":
                # Session-scoped values are per-connection; seed only global signals.
                try:
                    self._values[_value_key(spec.name, "")] = spec.initial()
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
            dep_audiences: list[SignalAudience] = []
            for dep in spec.deps:
                dep_spec = self._specs.get(dep)
                if dep_spec is not None:
                    dep_audiences.append(dep_spec.audience)
                    continue
                dep_derived = self._derived.get(dep)
                if dep_derived is not None:
                    dep_audiences.append(dep_derived.audience)
                    continue
                msg = f"derived signal {spec.name!r} depends on unknown signal {dep!r}"
                raise ValueError(msg)
            audience: SignalAudience = "session" if "session" in dep_audiences else "global"
            registered = DerivedSpec(
                name=spec.name,
                deps=spec.deps,
                compute=spec.compute,
                render=spec.render,
                audience=audience,
            )
            self._derived[spec.name] = registered
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
    def session_names(self) -> frozenset[str]:
        """Every registered signal or derived with ``audience="session"``."""
        with self._lock:
            primary = frozenset(n for n, s in self._specs.items() if s.audience == "session")
            derived = frozenset(n for n, d in self._derived.items() if d.audience == "session")
            return primary | derived

    @property
    def mixed_audience_derived_names(self) -> frozenset[str]:
        """Derived signals whose deps span both global and session audiences."""
        with self._lock:
            mixed: set[str] = set()
            for name, dspec in self._derived.items():
                audiences: set[SignalAudience] = set()
                for dep in dspec.deps:
                    dep_spec = self._specs.get(dep)
                    if dep_spec is not None:
                        audiences.add(dep_spec.audience)
                        continue
                    dep_derived = self._derived.get(dep)
                    if dep_derived is not None:
                        audiences.add(dep_derived.audience)
                if "global" in audiences and "session" in audiences:
                    mixed.add(name)
            return frozenset(mixed)

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

    def bind_backplane(self, plan: _SignalBackplanePlan) -> None:
        """Bind the freeze-compiled private plan exactly once."""
        with self._lock:
            if self._backplane_bound:
                raise RuntimeError("Signal backplane plan is already bound to this registry.")
            self._backplane = _SignalBackplaneCoordinator(plan, self.bus)
            self._backplane_bound = True

    @property
    def backplane_descriptor(self) -> _SignalBackplaneDescriptor | None:
        with self._lock:
            backplane = self._backplane
        return backplane.descriptor if backplane is not None else None

    @property
    def distributed(self) -> bool:
        with self._lock:
            backplane = self._backplane
        return backplane.distributed if backplane is not None else False

    async def start_backplane(self) -> None:
        with self._lock:
            backplane = self._backplane
        if backplane is not None:
            await backplane.start()

    async def close_backplane(self) -> None:
        with self._lock:
            backplane = self._backplane
        if backplane is not None:
            await backplane.close()

    async def subscribe_backplane(
        self, names: tuple[str, ...], *, audience_key: str
    ) -> AsyncIterator[_SignalUpdate]:
        """Yield rendered remote updates for exact authorized subjects."""
        with self._lock:
            backplane = self._backplane
        if backplane is None or not backplane.distributed:
            return
        subjects: dict[str, str] = {}
        for name in names:
            audience = self.audience_of(name)
            aud = audience_key if audience == "session" else ""
            publication = backplane.publication(
                name=name,
                data="",
                audience=audience,
                audience_key=aud,
            )
            subjects[publication.subject] = name
        async for update in backplane.subscribe(subjects):
            yield update

    def set_prefix_topics(self, mapping: Mapping[str, Iterable[str]]) -> None:
        """Configure optional URL-prefix → signal topics for proactive activation."""
        normalized: dict[str, frozenset[str]] = {}
        for prefix, names in mapping.items():
            if not isinstance(prefix, str) or not prefix.startswith("/"):
                msg = f"signal prefix topic key {prefix!r} must be an absolute path prefix"
                raise ValueError(msg)
            normalized[prefix] = frozenset(validate_signal_name(name) for name in names)
        with self._lock:
            self._prefix_topics = normalized

    def prefix_topics_for_path(self, path: str) -> frozenset[str]:
        """Return configured topics for the longest matching *path* prefix."""
        if not path:
            return frozenset()
        with self._lock:
            prefixes = self._prefix_topics
        best = ""
        topics: frozenset[str] = frozenset()
        for prefix, names in prefixes.items():
            if path.startswith(prefix) and len(prefix) > len(best):
                best = prefix
                topics = names
        return topics

    def expand_connection_topics(self, names: Iterable[str]) -> tuple[str, ...]:
        """Expand *names* with derived-signal dependency closures."""
        expanded = {validate_signal_name(name) for name in names}
        changed = True
        while changed:
            changed = False
            for name in list(expanded):
                with self._lock:
                    dspec = self._derived.get(name)
                if dspec is None:
                    continue
                for dep in dspec.deps:
                    if dep not in expanded:
                        expanded.add(dep)
                        changed = True
        return tuple(sorted(expanded))

    # -- value cache / SSR seed --

    def audience_of(self, name: str) -> SignalAudience:
        """Return whether *name* is ``global`` or ``session`` scoped."""
        return self._audience_of(name)

    def _audience_of(self, name: str) -> SignalAudience:
        with self._lock:
            spec = self._specs.get(name)
            if spec is not None:
                return spec.audience
            dspec = self._derived.get(name)
            if dspec is not None:
                return dspec.audience
        msg = f"signal {name!r} is not registered"
        raise KeyError(msg)

    def current_rendered(self, name: str, *, audience_key: str = "") -> str | None:
        """Return the SSR-seed string for *name*, or ``None`` if unseeded."""
        audience = self._audience_of(name)
        aud = audience_key if audience == "session" else ""
        key = _value_key(name, aud)
        with self._lock:
            spec = self._specs.get(name)
            if spec is not None:
                if key not in self._values:
                    return None
                value = self._values[key]
                renderer = spec
            else:
                dspec = self._derived.get(name)
                if dspec is None:
                    return None
                if key in self._values:
                    value = self._values[key]
                else:
                    dep_values = []
                    for dep in dspec.deps:
                        dep_spec = self._specs.get(dep)
                        dep_derived = self._derived.get(dep)
                        dep_audience = _dep_audience(dep_spec, dep_derived)
                        dep_aud = aud if dep_audience == "session" else ""
                        dep_values.append(self._values.get(_value_key(dep, dep_aud)))
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

    def emit(self, name: str, value: Any, *, audience_key: str = "") -> None:
        """Publish a new *value* for signal *name* and cascade to derived signals."""
        self._emit(name, value, audience_key=audience_key, local_only=False)

    def emit_local(self, name: str, value: Any, *, audience_key: str = "") -> None:
        """Connection-owned source emit that never crosses the Redis backplane."""
        self._emit(name, value, audience_key=audience_key, local_only=True)

    def _emit(
        self,
        name: str,
        value: Any,
        *,
        audience_key: str,
        local_only: bool,
    ) -> None:
        audience = self._audience_of(name)
        aud = audience_key if audience == "session" else ""
        if audience == "session" and not aud:
            msg = (
                f"session-scoped signal {name!r} requires a non-empty audience_key "
                "on emit (the visitor's session store key)"
            )
            raise ValueError(msg)
        key = _value_key(name, aud)
        with self._lock:
            if name not in self._specs and name not in self._derived:
                msg = (
                    f"signal {name!r} is not registered; declare it with "
                    "@app.signal or @app.derived before emitting"
                )
                raise KeyError(msg)
            spec = self._specs.get(name)
            backplane = self._backplane
            if (
                not local_only
                and spec is not None
                and not spec.coalesce
                and backplane is not None
                and backplane.distributed
            ):
                raise _SignalBackplaneError(
                    f"Redis-backed signal {name!r} uses coalesce=False, which requires "
                    "durable append delivery. Use coalesce=True or a single-worker "
                    "memory backplane."
                )
            prev_present = key in self._values
            prev = self._values.get(key)
            self._values[key] = value

        coalesce = spec.coalesce if spec is not None else True
        if coalesce and prev_present and _values_equal(prev, value):
            return

        self._publish(name, value, aud, local_only=local_only)
        self._cascade(name, aud, local_only=local_only)

    def seed(self, name: str, value: Any, *, audience_key: str = "") -> None:
        """Set the cached value without fan-out (SSR paint only)."""
        audience = self._audience_of(name)
        aud = audience_key if audience == "session" else ""
        if audience == "session" and not aud:
            msg = f"session-scoped signal {name!r} requires audience_key on seed"
            raise ValueError(msg)
        key = _value_key(name, aud)
        with self._lock:
            if name not in self._specs and name not in self._derived:
                msg = f"signal {name!r} is not registered"
                raise KeyError(msg)
            self._values[key] = value
        # Derived SSR seeds may depend on this — recompute derived cache quietly.
        self._seed_derived(name, aud)

    def _cascade(self, changed: str, audience_key: str, *, local_only: bool) -> None:
        """Recompute + re-emit every derived reachable from *changed*."""
        visited: set[str] = set()
        frontier = [changed]
        while frontier:
            source = frontier.pop(0)
            with self._lock:
                dependents = sorted(self._dependents.get(source, ()))
                pending: dict[str, tuple[DerivedSpec, list[Any | None]]] = {}
                for dname in dependents:
                    if dname not in self._derived or dname in visited:
                        continue
                    dspec = self._derived[dname]
                    dep_aud = audience_key if dspec.audience == "session" else ""
                    dep_values = []
                    for dep in dspec.deps:
                        dep_spec = self._specs.get(dep)
                        dep_derived = self._derived.get(dep)
                        dep_audience = _dep_audience(dep_spec, dep_derived)
                        dep_key_aud = dep_aud if dep_audience == "session" else ""
                        dep_values.append(self._values.get(_value_key(dep, dep_key_aud)))
                    pending[dname] = (dspec, dep_values)
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
                dep_aud = audience_key if dspec.audience == "session" else ""
                dkey = _value_key(dname, dep_aud)
                with self._lock:
                    prev_present = dkey in self._values
                    prev = self._values.get(dkey)
                    self._values[dkey] = derived_value
                if prev_present and _values_equal(prev, derived_value):
                    continue
                self._publish(dname, derived_value, dep_aud, local_only=local_only)
                frontier.append(dname)

    def _seed_derived(self, changed: str, audience_key: str) -> None:
        """Recompute derived values into the cache without publishing."""
        visited: set[str] = set()
        frontier = [changed]
        while frontier:
            source = frontier.pop(0)
            with self._lock:
                dependents = sorted(self._dependents.get(source, ()))
                pending: dict[str, tuple[DerivedSpec, list[Any | None]]] = {}
                for dname in dependents:
                    if dname not in self._derived or dname in visited:
                        continue
                    dspec = self._derived[dname]
                    dep_aud = audience_key if dspec.audience == "session" else ""
                    dep_values = []
                    for dep in dspec.deps:
                        dep_spec = self._specs.get(dep)
                        dep_derived = self._derived.get(dep)
                        dep_audience = _dep_audience(dep_spec, dep_derived)
                        dep_key_aud = dep_aud if dep_audience == "session" else ""
                        dep_values.append(self._values.get(_value_key(dep, dep_key_aud)))
                    pending[dname] = (dspec, dep_values)
            for dname, (dspec, dep_values) in pending.items():
                visited.add(dname)
                if any(v is None for v in dep_values):
                    continue
                try:
                    derived_value = dspec.compute(*dep_values)
                except Exception:
                    logger.exception(
                        "derived signal %r compute() failed on seed of %r", dname, source
                    )
                    continue
                dep_aud = audience_key if dspec.audience == "session" else ""
                with self._lock:
                    self._values[_value_key(dname, dep_aud)] = derived_value
                frontier.append(dname)

    def _publish(self, name: str, value: Any, audience_key: str, *, local_only: bool) -> None:
        """Render once on the emitter, then publish without holding the registry lock."""
        rendered = self.render_for_emit(name, value)
        if rendered is None:
            return
        audience = self._audience_of(name)
        with self._lock:
            backplane = self._backplane
            self._rendered_values[_value_key(name, audience_key)] = rendered
        if local_only or backplane is None:
            self.bus.emit_sync(
                ChangeEvent(
                    scope=_bus_scope(name, audience_key),
                    changed_paths=frozenset({_rendered_marker(name)}),
                )
            )
            return
        publication = backplane.publication(
            name=name,
            data=rendered,
            audience=audience,
            audience_key=audience_key,
        )
        backplane.publish(publication)

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

    def cached_value(self, name: str, *, audience_key: str = "") -> Any:
        """Return the cached raw value for *name* (``None`` if unset)."""
        audience = self._audience_of(name)
        aud = audience_key if audience == "session" else ""
        with self._lock:
            return self._values.get(_value_key(name, aud))

    def cached_rendered(self, name: str, *, audience_key: str = "") -> str | None:
        """Return the last emitter-rendered delivery payload for the memory bus."""
        audience = self._audience_of(name)
        aud = audience_key if audience == "session" else ""
        with self._lock:
            return self._rendered_values.get(_value_key(name, aud))


def _rendered_marker(name: str) -> str:
    """Marker path stored in a ChangeEvent for signal *name*."""
    return f"signal::{name}"


def _bus_scope(name: str, audience_key: str) -> str:
    """Opaque ReactiveBus scope for a process-local signal fan-out."""
    if not audience_key:
        return _SCOPE_PREFIX + name
    audience: SignalAudience = "session" if audience_key else "global"
    return signal_subject(
        _MEMORY_SUBJECT_KEY,
        audience=audience,
        audience_key=audience_key,
        name=name,
    )


def _value_key(name: str, audience_key: str) -> tuple[str, str]:
    return (audience_key, name)


def _dep_audience(spec: SignalSpec | None, derived: DerivedSpec | None) -> SignalAudience:
    """Return the audience of a registered dependency."""
    if spec is not None:
        return spec.audience
    if derived is not None:
        return derived.audience
    return "global"


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
