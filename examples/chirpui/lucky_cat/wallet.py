"""House-token wallet for Lucky Cat — the $MEOW balance behind the topbar.

#230 makes the Deposit shell action real. The deposit POST credits the house
token and the topbar balance re-renders via an OOB swap, so the example needs a
single source of truth for "how much $MEOW does the cat have?".

This is the example's first piece of mutable shared state, so it follows the
project store convention: a frozen-value balance guarded by a ``threading.Lock``
behind a tiny accessor. No DB, no persistence — the balance lives for the life
of the process and ``reset()`` restores the seed value for test isolation
(mirroring ``feed.reset()``).
"""

import threading
import time
from dataclasses import dataclass

# Starting balance — a lucky round number of house tokens.
INITIAL_MEOW = 1_000

_lock = threading.Lock()
_balance = INITIAL_MEOW


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


# Append-only deposit ledger, newest first. Guarded by the same ``_lock`` as the
# balance so a credit + its ledger entry land atomically and concurrent deposits
# can't interleave a half-written record. Cleared by ``reset()`` for test
# isolation (mirrors ``trade_store._history``).
_deposits: list[Deposit] = []


def balance() -> int:
    """Current $MEOW balance (sync, cheap — safe to read in a context provider)."""
    with _lock:
        return _balance


def deposit(amount: int) -> int:
    """Credit ``amount`` $MEOW, log it, and return the new balance.

    ``amount`` is clamped to ``>= 0`` so a malformed/negative form value can never
    debit the wallet. A zero credit (clamped bad input) is not ledgered — the
    statement only records real top-ups. Returns the post-deposit balance for the
    OOB re-render.
    """
    global _balance
    credit = max(0, int(amount))
    with _lock:
        _balance += credit
        if credit > 0:
            _deposits.insert(0, Deposit(amount=credit, balance_after=_balance, ts=time.time()))
        return _balance


def deposits(limit: int = 50) -> tuple[Deposit, ...]:
    """The deposit ledger, newest first (sync, cheap — safe in a context provider)."""
    with _lock:
        return tuple(_deposits[:limit])


def debit(amount: int) -> tuple[bool, int]:
    """Spend ``amount`` $MEOW, refusing to go negative.

    Returns ``(ok, balance)``: ``ok`` is ``True`` and the balance is debited
    only when the wallet can cover ``amount``; otherwise the balance is left
    untouched and ``ok`` is ``False``. ``amount`` is clamped to ``>= 0`` so a
    malformed/negative value can never *credit* via this path. This is the
    insufficient-balance gate the #225 trade flow checks before filling a buy.
    """
    global _balance
    spend = max(0, int(amount))
    with _lock:
        if spend > _balance:
            return (False, _balance)
        _balance -= spend
        return (True, _balance)


def reset() -> None:
    """Restore the seed balance and clear the ledger — used by the test fixture."""
    global _balance
    with _lock:
        _balance = INITIAL_MEOW
        _deposits.clear()
