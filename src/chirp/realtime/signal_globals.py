"""Template globals for the ``signal()`` primitive.

Three request-aware globals, registered at freeze **only when** signals exist:

- ``signal(name)`` — an SSR-seeded scalar sink:
  ``<span sse-swap="name" hx-target="this">{seed}</span>``. The seed is the
  current rendered value (from the value cache / ``spec.initial``) so there is no
  empty-then-fill flash; htmx's default ``sse-swap`` swap is ``innerHTML``.
- ``signal_block(name)`` — the same, for an HTML fragment, on a ``<div>``.
- ``signal_attrs(name)`` / ``signal_bind(name)`` — the binding **attributes only**
  (``sse-swap="name" hx-target="this"``) for an EXISTING element, so a layout's own
  semantic container (a CSS-grid ``<section>``, a ``<ul>``) becomes a live sink with
  no injected wrapper. The element keeps rendering its own SSR body; live events
  ``innerHTML``-swap it. Like ``signal()``/``signal_block()`` it records the topic and
  is detected by the dead-binding contract via the call-site, so the binding is
  validated even though the element's ``sse-swap`` is produced at render time.
  ``signal_bind`` is the preferred public name; ``signal_attrs`` is retained as an alias.
- ``signal_connect()`` — the **one** shared connection wrapper:
  ``<div hx-ext="sse" sse-connect="/_chirp/live?topics=..." hx-disinherit="...">``.
  All signal sinks on the page live inside this single wrapper; one connection
  carries every topic (the RFC's connection-budget win).

Each ``signal()`` / ``signal_block()`` call records the referenced name into a
request-scoped ``ContextVar`` so ``signal_connect()`` can scope the stream to the
topics actually used on this render. The globals build the seeded element with
``Markup`` (already-safe HTML), mirroring ``alpine_json_config``.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable
from html import escape
from typing import Any

from kida.template import Markup

from chirp.realtime.signals import SignalRegistry, validate_signal_name

#: Reserved framework prefix + path for the single merged signal stream.
SIGNAL_STREAM_PREFIX = "/_chirp"
SIGNAL_STREAM_PATH = "/_chirp/live"

#: Opening tag emitted by ``signal_connect()`` before end-of-render finalization.
#: ``apply_signal_connect()`` replaces this placeholder with a concrete
#: ``sse-connect`` URL scoped to the topics bound during the render.
_SIGNAL_CONNECT_OPEN = (
    '<div hx-ext="sse" data-chirp-signal-connect="" hx-disinherit="hx-target hx-swap">'
)

#: Per-render set of signal names referenced by ``signal()`` / ``signal_block()``.
#: ``signal_connect()`` reads it to scope the stream. Request-scoped so concurrent
#: renders (free-threading) never leak topics across each other.
_referenced: contextvars.ContextVar[set[str]] = contextvars.ContextVar("chirp_signals_referenced")

#: Per-request audience key for session-scoped signals (the visitor's store key).
#: ``signal_connect()`` appends ``?aud=…`` so ``/_chirp/live`` fans session signals
#: only to the matching connection. Empty means global-only bindings on this page.
_signal_audience: contextvars.ContextVar[str] = contextvars.ContextVar(
    "chirp_signal_audience", default=""
)

#: Request path for optional prefix-topic merge during connect finalization (#317).
_render_path: contextvars.ContextVar[str] = contextvars.ContextVar(
    "chirp_signal_render_path", default=""
)


def _record(name: str) -> None:
    try:
        names = _referenced.get()
    except LookupError:
        names = set()
        _referenced.set(names)
    names.add(name)


def reset_referenced() -> contextvars.Token[set[str]]:
    """Start a fresh per-render referenced-set. Returns a reset token."""
    return _referenced.set(set())


def restore_referenced(token: contextvars.Token[set[str]]) -> None:
    """Restore the referenced-set from a prior :func:`reset_referenced` token."""
    _referenced.reset(token)


def bind_signal_render_path(path: str) -> contextvars.Token[str]:
    """Bind the page path used for optional prefix-topic merge."""
    return _render_path.set(path)


def restore_signal_render_path(token: contextvars.Token[str]) -> None:
    _render_path.reset(token)


def _active_registry() -> SignalRegistry | None:
    """Return the active app's signal registry when rendering under a request."""
    from chirp.templating.integration import get_active_kida_env

    env = get_active_kida_env()
    if env is None:
        return None
    return getattr(env, "_chirp_signal_registry", None)


def _referenced_names() -> set[str]:
    try:
        return _referenced.get()
    except LookupError:
        return set()


def _connect_query() -> str:
    """Build the ``/_chirp/live`` query string from bound topics + audience."""
    parts: list[str] = []
    names = set(_referenced_names())
    registry = _active_registry()
    path = _render_path.get("")
    if registry is not None:
        if path:
            names |= registry.prefix_topics_for_path(path)
        if names:
            names = set(registry.expand_connection_topics(names))
    if names:
        parts.append(f"topics={','.join(sorted(names))}")
    aud = current_signal_audience()
    if aud:
        parts.append(f"aud={escape(aud, quote=True)}")
    if not parts:
        return ""
    return "?" + "&".join(parts)


def apply_signal_connect(html: str) -> str:
    """Finalize deferred ``signal_connect()`` placeholders in rendered HTML.

    ``signal_connect()`` emits a marker element at render time; once every
    ``signal()`` / ``signal_block()`` / ``signal_bind()`` on the page has
    recorded its topic, this patches the marker with the scoped ``sse-connect``
    URL. When no topics were bound, subscribe-all (bare ``/_chirp/live``).
    """
    if "data-chirp-signal-connect" not in html:
        return html
    url = f"{SIGNAL_STREAM_PATH}{_connect_query()}"
    replacement = f'<div hx-ext="sse" sse-connect="{url}" hx-disinherit="hx-target hx-swap">'
    return html.replace(_SIGNAL_CONNECT_OPEN, replacement)


def render_with_signal_finalize(render: Callable[[], str]) -> str:
    """Run *render* with a fresh referenced-set and finalize signal connects."""
    token = reset_referenced()
    try:
        html = render()
        return apply_signal_connect(html)
    finally:
        restore_referenced(token)


def set_signal_audience(audience_key: str) -> contextvars.Token[str]:
    """Bind the session audience key for session-scoped signal SSR + SSE."""
    return _signal_audience.set(audience_key)


def reset_signal_audience(token: contextvars.Token[str]) -> None:
    _signal_audience.reset(token)


def current_signal_audience() -> str:
    return _signal_audience.get()


def make_signal_globals(registry: SignalRegistry) -> dict[str, Any]:
    """Build the ``signal`` / ``signal_block`` / ``signal_connect`` globals."""

    def signal(name: str) -> Markup:
        """Emit an SSR-seeded scalar sink bound to signal *name*.

        ``<span sse-swap="name" hx-target="this">{seed}</span>`` — the seed is
        the current rendered value so the binding paints immediately, then every
        ``event: name`` ``innerHTML``-swaps it. Bind the same name in many places;
        they all stay in sync from the one shared connection.
        """
        validate_signal_name(name)
        _record(name)
        seed = registry.current_rendered(name, audience_key=current_signal_audience())
        inner = escape(seed) if seed is not None else ""
        return Markup(f'<span sse-swap="{escape(name)}" hx-target="this">{inner}</span>')

    def signal_block(name: str) -> Markup:
        """Emit an SSR-seeded HTML-fragment sink bound to signal *name*.

        Like :func:`signal` but on a ``<div>`` and the seed is treated as
        already-rendered HTML (the signal's ``render`` produced markup).
        """
        validate_signal_name(name)
        _record(name)
        seed = registry.current_rendered(name, audience_key=current_signal_audience())
        inner = seed if seed is not None else ""
        return Markup(f'<div sse-swap="{escape(name)}" hx-target="this">{inner}</div>')

    def signal_bind(name: str) -> Markup:
        """Emit binding attrs for an existing element bound to signal *name*.

        Returns ``sse-swap="name" hx-target="this"`` (no element, no wrapper) for
        placement inside an existing tag::

            <ul id="notif-list" {{ signal_bind('notifications') }}>
              {{ notification_list_body(notes) }}
            </ul>

        Use this when ``signal()``/``signal_block()`` would inject a ``<span>``/
        ``<div>`` that breaks the element's own layout (a CSS grid/flex container)
        or is otherwise wrong (binding a ``<ul>``). Unlike a hand-written
        ``sse-swap`` attribute, the ``signal_bind('x')`` CALL is recorded for topic
        scoping AND recognised by the dead-binding contract, so the binding is
        validated. The element must be a descendant of :func:`signal_connect`.
        """
        validate_signal_name(name)
        _record(name)
        return Markup(f'sse-swap="{escape(name)}" hx-target="this"')

    signal_attrs = signal_bind

    def signal_connect() -> Markup:
        """Emit the one shared ``sse-connect`` wrapper for all page signals.

        Emits a deferred connect marker; :func:`apply_signal_connect` patches it
        at end-of-render with ``?topics=`` scoped to every
        ``signal()`` / ``signal_block()`` / ``signal_bind()`` call on the page.
        That fixes composed-layout ordering (the connect often renders before
        body bindings record) and lets ``/_chirp/live`` pump only the bound
        async sources. When no topics were bound, subscribe-all (bare stream).

        Prefer ``signal_bind()`` over hand-written ``sse-swap`` so manual sinks
        participate in topic discovery. Place this once in the shell; every
        signal sink must live as a descendant — htmx ``sse-swap`` binds via
        ``querySelectorAll``, which excludes the connect element itself.
        """
        return Markup(_SIGNAL_CONNECT_OPEN)

    return {
        "signal": signal,
        "signal_block": signal_block,
        "signal_bind": signal_bind,
        "signal_attrs": signal_attrs,
        "signal_connect": signal_connect,
    }
