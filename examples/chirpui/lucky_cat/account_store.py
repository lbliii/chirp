"""DOMAIN — house-token account boundary for Lucky Cat.

The ``AccountStore`` protocol and two shipped implementations:

* ``InMemoryAccountStore`` — a standalone process-local ledger (the reference
  impl, like ``SimFeed`` for market data).
* ``SessionAccountStore`` — the default from :func:`get_account`; delegates to
  :mod:`session_store` so each browser session owns an isolated balance (#285).

Framework code never touches a ledger directly — routes and pages call
``wallet.balance()`` / ``wallet.deposit()`` (thin wrappers) or
``get_account()`` for the protocol surface. A shared Redis/Postgres ledger is
out of scope; only the protocol seam and the in-memory/session impls ship.

Pure stdlib only (``threading``, ``time``, ``dataclasses``); importing this
module does not re-enable the GIL on a 3.14t build.
"""

import os
import threading
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import session_store

# Starting balance — a lucky round number of house tokens.
INITIAL_MEOW = 100_000


@dataclass(frozen=True, slots=True)
class Deposit:
    """An append-only credit record — drives the Activity → Deposits view.

    ``amount`` is the credited $MEOW; ``balance_after`` is the post-credit
    balance (so the ledger reads like a real statement); ``ts`` is the
    wall-clock epoch of the credit.
    """

    amount: int
    balance_after: int
    ts: float


@runtime_checkable
class AccountStore(Protocol):
    """Source-agnostic $MEOW account boundary.

    Snapshot methods are sync and cheap (safe to call from a context provider /
    page handler). ``credit`` / ``debit`` mutate the balance under the store's
    lock; ``deposits`` is the append-only ledger (newest first).
    """

    def balance(self) -> int:
        """Current $MEOW balance."""
        ...

    def credit(self, amount: int) -> int:
        """Credit ``amount`` $MEOW and return the new balance."""
        ...

    def debit(self, amount: int) -> tuple[bool, int]:
        """Spend ``amount`` $MEOW; return ``(ok, balance)``."""
        ...

    def deposits(self, limit: int = 50) -> tuple[Deposit, ...]:
        """Deposit ledger, newest first."""
        ...

    def reset(self) -> None:
        """Restore seed balance and clear the ledger — test isolation."""
        ...


class InMemoryAccountStore:
    """Standalone process-local $MEOW ledger — ``LUCKY_CAT_ACCOUNT=memory`` ref impl."""

    def __init__(self, initial_balance: int = INITIAL_MEOW) -> None:
        self._initial_balance = initial_balance
        self._lock = threading.Lock()
        self._balance = initial_balance
        self._deposits: list[Deposit] = []

    def balance(self) -> int:
        with self._lock:
            return self._balance

    def credit(self, amount: int) -> int:
        credit = max(0, int(amount))
        with self._lock:
            self._balance += credit
            if credit > 0:
                self._deposits.insert(
                    0,
                    Deposit(amount=credit, balance_after=self._balance, ts=time.time()),
                )
            return self._balance

    def debit(self, amount: int) -> tuple[bool, int]:
        spend = max(0, int(amount))
        with self._lock:
            if spend > self._balance:
                return (False, self._balance)
            self._balance -= spend
            return (True, self._balance)

    def deposits(self, limit: int = 50) -> tuple[Deposit, ...]:
        with self._lock:
            return tuple(self._deposits[:limit])

    def reset(self) -> None:
        with self._lock:
            self._balance = self._initial_balance
            self._deposits.clear()


class SessionAccountStore:
    """Session-scoped ``AccountStore`` — the default ``get_account()`` impl."""

    def __init__(self, initial_balance: int = INITIAL_MEOW) -> None:
        self._initial_balance = initial_balance

    def balance(self) -> int:
        with session_store.locked(balance_seed=self._initial_balance) as state:
            return state.wallet.balance

    def credit(self, amount: int) -> int:
        credit = max(0, int(amount))
        with session_store.locked(balance_seed=self._initial_balance) as state:
            state.wallet.balance += credit
            if credit > 0:
                state.wallet.deposits.insert(
                    0,
                    Deposit(
                        amount=credit,
                        balance_after=state.wallet.balance,
                        ts=time.time(),
                    ),
                )
            return state.wallet.balance

    def debit(self, amount: int) -> tuple[bool, int]:
        spend = max(0, int(amount))
        with session_store.locked(balance_seed=self._initial_balance) as state:
            if spend > state.wallet.balance:
                return (False, state.wallet.balance)
            state.wallet.balance -= spend
            return (True, state.wallet.balance)

    def deposits(self, limit: int = 50) -> tuple[Deposit, ...]:
        with session_store.locked(balance_seed=self._initial_balance) as state:
            return tuple(state.wallet.deposits[:limit])

    def reset(self) -> None:
        session_store.reset()


# ---------------------------------------------------------------------------
# Store selector — LUCKY_CAT_ACCOUNT (default "session"). Cached singleton.
# ---------------------------------------------------------------------------

_account_lock = threading.Lock()
_account: AccountStore | None = None


def _build_account() -> AccountStore:
    source = os.environ.get("LUCKY_CAT_ACCOUNT", "session").strip().lower()
    if source == "memory":
        return InMemoryAccountStore()
    if source != "session":
        import logging

        logging.getLogger("lucky_cat.account_store").warning(
            "LUCKY_CAT_ACCOUNT=%r is not available (shared ledger adapters are out of "
            "scope); falling back to SessionAccountStore.",
            source,
        )
    return SessionAccountStore()


def get_account() -> AccountStore:
    """Return the cached account store selected by ``LUCKY_CAT_ACCOUNT``."""
    global _account
    if _account is None:
        with _account_lock:
            if _account is None:
                _account = _build_account()
    return _account


def reset() -> None:
    """Reset account state. Used by tests / conftest."""
    global _account
    session_store.reset()
    with _account_lock:
        if isinstance(_account, InMemoryAccountStore):
            _account.reset()
