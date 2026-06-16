"""Per-visitor ephemeral store registry — session-keyed mutable demo state (#285).

Lucky Cat keeps wallet, trades, watchlist, and notifications in process memory.
Each browser session gets an isolated :class:`StoreState` bucket keyed by
``__store_key`` in the signed session (assigned on first store touch). Auth
identity stays the shared ``neko`` demo account; **state** is per-session so
concurrent demo visitors cannot stomp each other's balances.

Idle sessions are swept after :data:`IDLE_TTL_S` and the registry is capped at
:data:`MAX_SESSIONS` (LRU eviction). ``reset()`` clears everything for tests.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from chirp.middleware.sessions import get_session

# Fallback bucket for direct module calls outside a request (unit tests).
DEFAULT_KEY = "__default__"

# 30 minutes idle, ~500 concurrent visitors.
IDLE_TTL_S = 30 * 60
MAX_SESSIONS = 500

_lock = threading.Lock()
_sessions: dict[str, _Entry] = {}

# Optional override for tests that assert store state outside a live request.
_key_override: ContextVar[str | None] = ContextVar("lucky_cat_store_key", default=None)


@dataclass(slots=True)
class WalletSlice:
    balance: int
    deposits: list  # wallet.Deposit — typed lazily to avoid import cycles


@dataclass(slots=True)
class TradeSlice:
    positions: dict
    open_orders: dict
    history: list
    next_order_id: int


@dataclass(slots=True)
class NotificationSlice:
    log: list
    next_id: int
    read_through_id: int


@dataclass(slots=True)
class StoreState:
    """All per-session mutable state behind the demo account surfaces."""

    wallet: WalletSlice
    trade: TradeSlice
    starred: set[str] = field(default_factory=set)
    notifications: NotificationSlice | None = None


@dataclass(slots=True)
class _Entry:
    state: StoreState
    last_access: float


def _seed_state(*, balance: int) -> StoreState:
    return StoreState(
        wallet=WalletSlice(balance=balance, deposits=[]),
        trade=TradeSlice(positions={}, open_orders={}, history=[], next_order_id=1),
        starred=set(),
        notifications=NotificationSlice(log=[], next_id=1, read_through_id=0),
    )


def session_key() -> str:
    """Return the store key for the current request, test override, or default."""
    try:
        session = get_session()
    except LookupError:
        session = None
    if session is not None:
        key = session.get("__store_key")
        if isinstance(key, str) and key:
            return key
    override = _key_override.get()
    if override is not None:
        return override
    return DEFAULT_KEY


def ensure_store_key() -> None:
    """Assign ``__store_key`` on first touch so each browser cookie is unique."""
    try:
        session = get_session()
    except LookupError:
        return
    if not session.get("__store_key"):
        session["__store_key"] = str(uuid.uuid4())


@contextmanager
def locked(*, balance_seed: int) -> Iterator[StoreState]:
    """Yield the current session's :class:`StoreState` under the registry lock."""
    key = session_key()
    now = time.monotonic()
    with _lock:
        _sweep_locked(now)
        entry = _sessions.get(key)
        if entry is None:
            if len(_sessions) >= MAX_SESSIONS:
                _evict_lru_locked()
            entry = _Entry(state=_seed_state(balance=balance_seed), last_access=now)
            _sessions[key] = entry
        else:
            entry.last_access = now
        yield entry.state


def client_keys() -> frozenset[str]:
    """Non-default session keys currently in the registry (test helper)."""
    with _lock:
        return frozenset(k for k in _sessions if k != DEFAULT_KEY)


def latest_client_key() -> str:
    """The most recently touched non-default session key (test helper)."""
    with _lock:
        candidates = {k: e for k, e in _sessions.items() if k != DEFAULT_KEY}
        if not candidates:
            msg = "no client session store exists"
            raise LookupError(msg)
        return max(candidates.items(), key=lambda item: item[1].last_access)[0]


def balance_for_key(key: str, *, balance_seed: int) -> int:
    """Read the wallet balance for an explicit session key."""
    with _lock:
        entry = _sessions.get(key)
        if entry is None:
            return balance_seed
        return entry.state.wallet.balance


def reset() -> None:
    """Clear every session bucket — wired into ``conftest.py``."""
    global _sessions
    with _lock:
        _sessions = {}


@contextmanager
def bind(key: str) -> Iterator[None]:
    """Bind store accessors to ``key`` for the duration of a test block."""
    token = _key_override.set(key)
    try:
        yield
    finally:
        _key_override.reset(token)


def broadcast_notifications(callback) -> None:
    """Mutate every session's notification slice under the registry lock."""
    now = time.monotonic()
    with _lock:
        for entry in _sessions.values():
            notes = entry.state.notifications
            assert notes is not None
            callback(notes)
            entry.last_access = now


def _sweep_locked(now: float) -> None:
    stale = [k for k, e in _sessions.items() if now - e.last_access > IDLE_TTL_S]
    for k in stale:
        del _sessions[k]


def _evict_lru_locked() -> None:
    if not _sessions:
        return
    oldest = min(_sessions.items(), key=lambda item: item[1].last_access)[0]
    del _sessions[oldest]
