"""Template globals for the ``signal()`` primitive.

Three request-aware globals, registered at freeze **only when** signals exist:

- ``signal(name)`` — an SSR-seeded scalar sink:
  ``<span sse-swap="name" hx-target="this">{seed}</span>``. The seed is the
  current rendered value (from the value cache / ``spec.initial``) so there is no
  empty-then-fill flash; htmx's default ``sse-swap`` swap is ``innerHTML``.
- ``signal_block(name)`` — the same, for an HTML fragment, on a ``<div>``.
- ``signal_attrs(name)`` — the binding **attributes only**
  (``sse-swap="name" hx-target="this"``) for an EXISTING element, so a layout's own
  semantic container (a CSS-grid ``<section>``, a ``<ul>``) becomes a live sink with
  no injected wrapper. The element keeps rendering its own SSR body; live events
  ``innerHTML``-swap it. Like ``signal()``/``signal_block()`` it records the topic and
  is detected by the dead-binding contract via the call-site, so the binding is
  validated even though the element's ``sse-swap`` is produced at render time.
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
from html import escape
from typing import Any

from kida.template import Markup

from chirp.realtime.signals import SignalRegistry, validate_signal_name

#: Reserved framework prefix + path for the single merged signal stream.
SIGNAL_STREAM_PREFIX = "/_chirp"
SIGNAL_STREAM_PATH = "/_chirp/live"

#: Per-render set of signal names referenced by ``signal()`` / ``signal_block()``.
#: ``signal_connect()`` reads it to scope the stream. Request-scoped so concurrent
#: renders (free-threading) never leak topics across each other.
_referenced: contextvars.ContextVar[set[str]] = contextvars.ContextVar("chirp_signals_referenced")

#: Per-request audience key for session-scoped signals (the visitor's store key).
#: ``signal_connect()`` appends ``?aud=…`` so ``/_chirp/live`` fans session signals
#: only to the matching connection. Empty means global-only bindings on this page.
_signal_audience: contextvars.ContextVar[str] = contextvars.ContextVar("chirp_signal_audience", default="")


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

    def signal_attrs(name: str) -> Markup:
        """Emit the binding ATTRIBUTES for an existing element bound to signal *name*.

        Returns ``sse-swap="name" hx-target="this"`` (no element, no wrapper) for
        placement inside an existing tag::

            <section class="board" {{ signal_attrs('market_stats') }}>
              {{ stat_strip_body(stats) }}   {#- the element renders its own SSR body -#}
            </section>

        Use this when ``signal()``/``signal_block()`` would inject a ``<span>``/
        ``<div>`` that breaks the element's own layout (a CSS grid/flex container)
        or is otherwise wrong (binding a ``<ul>``). Unlike a hand-written
        ``sse-swap`` attribute, the ``signal_attrs('x')`` CALL is recorded for topic
        scoping AND recognised by the dead-binding contract, so the binding is
        validated. The element must be a descendant of :func:`signal_connect`.
        """
        validate_signal_name(name)
        _record(name)
        return Markup(f'sse-swap="{escape(name)}" hx-target="this"')

    def signal_connect() -> Markup:
        """Emit the one shared ``sse-connect`` wrapper for all page signals.

        **Subscribe-all:** emits the bare stream URL so EVERY registered signal is
        delivered, regardless of where its binding sits. Per-page ``?topics=``
        scoping is unsound as a default here for two reasons: (1) bindings on
        *existing* shell elements use a manual ``sse-swap`` attribute rather than
        the ``signal()`` / ``signal_block()`` helpers, so they never record a
        topic; (2) in a composed layout the connect element often renders before
        some bindings record. Most signals are global shell chrome (a balance, a
        ticker, a notifications bell) that must update on every page anyway, and an
        event with no matching ``sse-swap`` is a harmless htmx no-op — so
        subscribe-all is correct. Topic scoping is a future bandwidth optimization,
        opt-in once binding discovery is reliable.

        Place this once in the shell; every ``signal()`` / ``signal_block()`` sink
        (and every manual ``sse-swap`` sink) must live as a descendant — htmx
        ``sse-swap`` binds via ``querySelectorAll``, which excludes the connect
        element itself.
        """
        return Markup(
            f'<div hx-ext="sse" sse-connect="{SIGNAL_STREAM_PATH}{_audience_query()}" '
            'hx-disinherit="hx-target hx-swap">'
        )

    def _audience_query() -> str:
        aud = current_signal_audience()
        if not aud:
            return ""
        return f"?aud={escape(aud, quote=True)}"

    return {
        "signal": signal,
        "signal_block": signal_block,
        "signal_attrs": signal_attrs,
        "signal_connect": signal_connect,
    }
