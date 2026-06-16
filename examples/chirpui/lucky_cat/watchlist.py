"""Watchlist store for Lucky Cat — the starred markets behind the Favorites rail lane.

The starred set backs the Markets-room **Favorites** destination. Per-visitor
state (#285): membership is keyed by browser session via :mod:`session_store`.

Convention: session-scoped mutable state behind the registry lock, immutable
snapshots out, and ``reset()`` for test isolation.
"""

import session_store
from wallet import INITIAL_MEOW


def contains(symbol: str) -> bool:
    """True when ``symbol`` is starred (sync, cheap — safe in a context provider)."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        return symbol in state.starred


def symbols() -> frozenset[str]:
    """An immutable snapshot of the starred symbols (sync, cheap)."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        return frozenset(state.starred)


def count() -> int:
    """How many markets are starred — the rail badge figure."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        return len(state.starred)


def add(symbol: str) -> bool:
    """Star ``symbol`` (idempotent). Returns the post-add starred state (``True``)."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        state.starred.add(symbol)
        return True


def remove(symbol: str) -> bool:
    """Unstar ``symbol`` (idempotent). Returns the post-remove starred state."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        state.starred.discard(symbol)
        return False


def toggle(symbol: str) -> bool:
    """Flip ``symbol``'s starred state atomically and return the NEW state."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        if symbol in state.starred:
            state.starred.discard(symbol)
            return False
        state.starred.add(symbol)
        return True


def reset() -> None:
    """Clear every session bucket — used by the test fixture."""
    session_store.reset()
