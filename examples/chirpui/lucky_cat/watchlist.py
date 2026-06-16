"""Watchlist store for Lucky Cat — the starred markets behind the Favorites rail lane.

The starred set backs the Markets-room **Favorites** destination: the rail's
Favorites lane links to the real ``/markets/favorites`` page (one of the four
fixed Markets destinations, moved here from ``/watchlist`` in #282) that renders
only the markets the user has starred, with a live count badge in the inner rail.

Like ``wallet.py`` / ``notifications.py`` / ``trade_store.py`` it is the
example's mutable shared state, so it follows the same store convention: a single
``threading.Lock`` behind tiny accessors, immutable snapshots out, and a
``reset()`` for test isolation (wired into ``conftest.py`` alongside
``feed.reset()`` / ``wallet.reset()`` / ``trade_store.reset()`` /
``notifications.reset()``).

Single source of truth: every star toggle goes through :func:`toggle` (or the
idempotent :func:`add` / :func:`remove`), so the rail count badge can never drift
from the set the ``/markets/favorites`` page renders. The starred set is a plain
``set`` of symbol strings guarded by ``_lock``.

Free-threading safety (this example's whole point): the set lives under one
``_lock``, so concurrent toggles from racing route handlers can interleave
without corrupting the membership or the derived count. Snapshot reads
(:func:`symbols` / :func:`count` / :func:`contains`) take the lock and copy, so a
reader never sees a half-mutated set.

Pure stdlib only (``threading``); importing this module does not re-enable the
GIL on a 3.14t build.
"""

import threading

# Module state — the starred symbols, guarded by one lock. Seeded empty: the
# user stars markets to populate the watchlist (no pre-starred defaults, so the
# empty state is the first thing a fresh visitor sees).
_lock = threading.Lock()
_starred: set[str] = set()


def contains(symbol: str) -> bool:
    """True when ``symbol`` is starred (sync, cheap — safe in a context provider)."""
    with _lock:
        return symbol in _starred


def symbols() -> frozenset[str]:
    """An immutable snapshot of the starred symbols (sync, cheap).

    Returns a ``frozenset`` so a caller can test membership / iterate without
    holding the lock and can never mutate the live set.
    """
    with _lock:
        return frozenset(_starred)


def count() -> int:
    """How many markets are starred — the rail badge figure."""
    with _lock:
        return len(_starred)


def add(symbol: str) -> bool:
    """Star ``symbol`` (idempotent). Returns the post-add starred state (``True``)."""
    with _lock:
        _starred.add(symbol)
        return True


def remove(symbol: str) -> bool:
    """Unstar ``symbol`` (idempotent). Returns the post-remove starred state
    (``False``)."""
    with _lock:
        _starred.discard(symbol)
        return False


def toggle(symbol: str) -> bool:
    """Flip ``symbol``'s starred state atomically and return the NEW state.

    The single source of truth for the star control: add when absent, remove when
    present, all inside one lock so a racing double-toggle can never leave the set
    in an inconsistent state or miscount. Returns ``True`` when the symbol is now
    starred, ``False`` when it is now unstarred — the value the OOB star twin
    renders ``aria-pressed`` / the ★/☆ glyph from.
    """
    with _lock:
        if symbol in _starred:
            _starred.discard(symbol)
            return False
        _starred.add(symbol)
        return True


def reset() -> None:
    """Clear the starred set to the empty seed — used by the test fixture."""
    with _lock:
        _starred.clear()
