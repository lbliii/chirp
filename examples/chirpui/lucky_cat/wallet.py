"""House-token wallet for Lucky Cat — the $MEOW balance behind the topbar.

#230 makes the Deposit shell action real. The deposit POST credits the house
token and the topbar balance re-renders via the live ``balance`` signal.

Per-visitor state (#285): balances live in :mod:`session_store` keyed by the
browser session's ``__store_key``. This module keeps the thin function API the
example imports; mutable state sits behind :func:`account_store.get_account`
(``AccountStore`` protocol / ``SessionAccountStore`` default).
"""

from account_store import INITIAL_MEOW, Deposit, get_account

__all__ = ("INITIAL_MEOW", "Deposit", "balance", "debit", "deposit", "deposits", "reset")


def balance() -> int:
    """Current $MEOW balance (sync, cheap — safe to read in a context provider)."""
    return get_account().balance()


def deposit(amount: int) -> int:
    """Credit ``amount`` $MEOW, log it, and return the new balance."""
    return get_account().credit(amount)


def deposits(limit: int = 50) -> tuple[Deposit, ...]:
    """The deposit ledger, newest first (sync, cheap — safe in a context provider)."""
    return get_account().deposits(limit)


def debit(amount: int) -> tuple[bool, int]:
    """Spend ``amount`` $MEOW, refusing to go negative."""
    return get_account().debit(amount)


def reset() -> None:
    """Restore the seed balance and clear the ledger — used by the test fixture."""
    from account_store import reset as reset_account

    reset_account()
