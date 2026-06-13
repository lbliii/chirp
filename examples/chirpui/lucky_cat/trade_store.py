"""Thread-safe trading store for Lucky Cat — the M2 mutation backend (#225).

This is the single source of truth the place/cancel-order flow (#225) writes
and the portfolio Suspense dashboard (#224) reads. It layers on two existing
seams:

* ``wallet.py`` — the cash side of the house token ($MEOW). A buy debits cash
  via ``wallet.debit``; a sell credits it via ``wallet.deposit``.
* ``feed.py`` ``SimFeed`` — live (simulated) prices via ``get_feed().ticker``.
  Market orders fill at the current ticker price; limit orders fill at their
  limit price (M2 is an always-fill sim — see :func:`place_order`).

Convention (mirrors ``wallet.py`` / ``kanban_shell``'s ``store.py``): frozen
dataclass models, module-level mutable state guarded by a single
``threading.Lock``, and a ``reset()`` for test isolation (wired into
``conftest.py`` alongside ``feed.reset()`` / ``wallet.reset()``).

Free-threading note: every store method takes ``_lock``; price reads call
``get_feed().ticker()`` (itself guarded by ``SimFeed._lock``). To avoid
lock-ordering hazards we **snapshot the price first, then take ``_lock``** —
the two locks are never held across one another.
"""

import threading
import time
from dataclasses import dataclass, replace

import wallet
from feed import get_feed

# Per-order minimum notional ($MEOW). A floor that keeps dust orders out and
# gives the "below min size" validation branch something honest to reject.
MIN_NOTIONAL_MEOW = 1.0


# ---------------------------------------------------------------------------
# Models — frozen dataclasses (slots=True). Same objects flow from the store
# through the context provider into the templates; no serialization layer.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Position:
    """A net long holding in a base asset; ``avg_price`` is the cost basis in $MEOW."""

    symbol: str
    size: float
    avg_price: float


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    symbol: str
    side: str  # "buy" | "sell"
    kind: str  # "market" | "limit"
    size: float
    limit_price: float | None
    status: str  # "open" | "filled" | "cancelled"
    ts: float


@dataclass(frozen=True, slots=True)
class Fill:
    """Append-only execution record — drives the activity / history view."""

    order_id: int
    symbol: str
    side: str
    size: float
    price: float
    ts: float


# ---------------------------------------------------------------------------
# Module state — all under one lock. Seeded empty: the wallet's INITIAL_MEOW is
# the only starting cash; zero positions, zero open orders.
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_positions: dict[str, Position] = {}
_open_orders: dict[int, Order] = {}
_history: list[Fill] = []
_next_order_id: int = 1


# ---------------------------------------------------------------------------
# Validation — hand-rolled dict[str, list[str]] (kanban's validate_task idiom).
# ---------------------------------------------------------------------------


def _known_symbols() -> set[str]:
    return {m.symbol for m in get_feed().markets()}


def validate_order(
    symbol: str,
    side: str,
    kind: str,
    size_raw: str,
    limit_raw: str,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """Validate raw form values, returning ``(errors, parsed)``.

    ``errors`` is a ``dict[str, list[str]]`` keyed by field name (``_form`` for
    form-level). ``parsed`` carries the coerced ``size`` / ``limit_price`` /
    ``fill_price`` so a clean result can fill without re-parsing. Price reads
    happen here (before ``_lock`` is taken in :func:`place_order`).
    """
    errors: dict[str, list[str]] = {}
    parsed: dict[str, object] = {}

    if symbol not in _known_symbols():
        errors.setdefault("symbol", []).append("Pick a market.")
    if side not in ("buy", "sell"):
        errors.setdefault("side", []).append("Choose buy or sell.")
    if kind not in ("market", "limit"):
        errors.setdefault("kind", []).append("Choose market or limit.")

    # Size.
    try:
        size = float(size_raw)
    except ValueError, TypeError:
        size = 0.0
        errors.setdefault("size", []).append("Enter a valid size.")
    else:
        if size <= 0:
            errors.setdefault("size", []).append("Size must be greater than zero.")
    parsed["size"] = size

    # Limit price (only meaningful for limit kind).
    limit_price: float | None = None
    if kind == "limit":
        try:
            limit_price = float(limit_raw)
        except ValueError, TypeError:
            limit_price = None
            errors.setdefault("limit_price", []).append("Enter a valid limit price.")
        else:
            if limit_price <= 0:
                limit_price = None
                errors.setdefault("limit_price", []).append("Enter a valid limit price.")
    parsed["limit_price"] = limit_price

    # Anything below depends on a known symbol + a sane size. Snapshot the price
    # *here* (SimFeed._lock) so place_order never holds two locks at once.
    if "symbol" in errors or "size" in errors:
        return errors, parsed

    fill_price = limit_price if kind == "limit" else get_feed().ticker(symbol).price
    parsed["fill_price"] = fill_price
    if fill_price is None:
        return errors, parsed

    notional = size * fill_price
    if notional < MIN_NOTIONAL_MEOW:
        errors.setdefault("size", []).append(
            f"Minimum order size is {MIN_NOTIONAL_MEOW:g} $MEOW notional."
        )

    if side == "buy":
        bal = wallet.balance()
        if notional > bal:
            errors.setdefault("size", []).append(f"Not enough $MEOW. You have {bal}.")
    else:  # sell
        held = _position_size(symbol)
        if size > held:
            errors.setdefault("size", []).append(f"You only hold {held:g} {symbol.split('-')[0]}.")

    return errors, parsed


def _position_size(symbol: str) -> float:
    with _lock:
        pos = _positions.get(symbol)
        return pos.size if pos is not None else 0.0


# ---------------------------------------------------------------------------
# Mutations.
# ---------------------------------------------------------------------------


def try_place_order(
    symbol: str,
    side: str,
    kind: str,
    size: float,
    limit_price: float | None = None,
    *,
    fill_price: float | None = None,
) -> tuple[Order | None, dict[str, list[str]]]:
    """Atomically validate-and-fill an order — concurrency-safe, never raises.

    Returns ``(order, errors)``: on a clean fill ``(filled Order, {})``; when a
    buy cannot be covered ``(None, {"size": [...]})`` — a :class:`ValidationError`
    422, never an exception. This is the free-threading-safe entry point the
    ``/trade/order`` handler uses.

    The race this closes: :func:`validate_order` reads ``wallet.balance()``
    *outside* any cross-call lock, and the old ``place_order`` then debited and
    *raised* on a failed debit. Two concurrent buys could both pass validation
    against the same balance, then one debit fail → unhandled ``ValueError`` →
    500. Here the balance re-check **and** the debit happen inside a single
    ``_lock`` critical section, so only one of two racing buys wins and the loser
    gets a clean 422 — no 500, no double-spend.

    Lock ordering: ``_lock`` is taken first, then ``wallet`` is mutated under it
    (``wallet.balance`` / ``wallet.debit`` / ``wallet.deposit`` each take their
    own ``wallet._lock`` inside). No path ever takes ``wallet._lock`` and then
    ``_lock``, so this nesting is deadlock-free. Prices are snapshotted *before*
    ``_lock`` (``fill_price``), so ``feed._lock`` is never held across ``_lock``.
    """
    if fill_price is None:
        fill_price = limit_price if kind == "limit" else get_feed().ticker(symbol).price
    price = float(fill_price)
    notional = size * price
    cost = round(notional)
    ts = time.time()

    global _next_order_id
    with _lock:
        if side == "buy":
            # Re-check + debit atomically: wallet.debit refuses to go negative,
            # so a racing buy that no longer fits simply returns ok=False here.
            ok, bal = wallet.debit(cost)
            if not ok:
                return None, {
                    "size": [f"Not enough $MEOW. You have {bal}."],
                }
        else:
            # Selling credits the wallet (clamped to >= 0 inside deposit).
            wallet.deposit(cost)

        order_id = _next_order_id
        _next_order_id += 1
        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            kind=kind,
            size=size,
            limit_price=limit_price,
            status="filled",
            ts=ts,
        )
        _apply_fill_locked(symbol, side, size, price)
        _history.insert(0, Fill(order_id, symbol, side, size, price, ts))
        return order, {}


def place_order(
    symbol: str,
    side: str,
    kind: str,
    size: float,
    limit_price: float | None = None,
    *,
    fill_price: float | None = None,
) -> Order:
    """Fill an order at the current price (M2 always-fill sim) and book it.

    Thin wrapper over :func:`try_place_order` that returns the :class:`Order`
    directly, raising ``ValueError`` if the wallet cannot cover a buy. The
    ``/trade/order`` handler uses :func:`try_place_order` for its clean-422
    contract; this raising form stays for tests and direct callers that have
    already gated the buy via :func:`validate_order`.
    """
    order, _errors = try_place_order(symbol, side, kind, size, limit_price, fill_price=fill_price)
    if order is None:
        raise ValueError("insufficient balance")
    return order


def _apply_fill_locked(symbol: str, side: str, size: float, price: float) -> None:
    """Update the net position for a fill. Caller holds ``_lock``."""
    pos = _positions.get(symbol)
    cur_size = pos.size if pos is not None else 0.0
    cur_avg = pos.avg_price if pos is not None else 0.0

    if side == "buy":
        new_size = cur_size + size
        # Weighted-average cost basis.
        new_avg = ((cur_size * cur_avg) + (size * price)) / new_size if new_size else price
    else:  # sell — reduce the position, basis unchanged.
        new_size = cur_size - size
        new_avg = cur_avg

    if new_size <= 1e-9:
        _positions.pop(symbol, None)
    elif pos is None:
        _positions[symbol] = Position(symbol=symbol, size=new_size, avg_price=new_avg)
    else:
        _positions[symbol] = replace(pos, size=new_size, avg_price=new_avg)


def open_limit_order(
    symbol: str,
    side: str,
    size: float,
    limit_price: float,
) -> Order:
    """Book a resting (unfilled) limit order — exercises the open-order count.

    M2 keeps this distinct from :func:`place_order` so the demo can show a
    non-empty open-orders list and a live count badge without a matching engine.
    """
    global _next_order_id
    with _lock:
        order_id = _next_order_id
        _next_order_id += 1
        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            kind="limit",
            size=size,
            limit_price=limit_price,
            status="open",
            ts=time.time(),
        )
        _open_orders[order_id] = order
        return order


def cancel_order(order_id: int) -> Order | None:
    """Flip an open order to ``cancelled``. Returns it, or ``None`` if unknown."""
    with _lock:
        order = _open_orders.pop(order_id, None)
        if order is None:
            return None
        return replace(order, status="cancelled")


# ---------------------------------------------------------------------------
# Reads (sync, cheap — safe in context providers / asyncio.to_thread loaders).
# ---------------------------------------------------------------------------


def positions() -> tuple[Position, ...]:
    """Non-zero holdings, stable-sorted by symbol."""
    with _lock:
        return tuple(sorted(_positions.values(), key=lambda p: p.symbol))


def position(symbol: str) -> Position | None:
    with _lock:
        return _positions.get(symbol)


def open_orders() -> tuple[Order, ...]:
    """Resting orders, newest first."""
    with _lock:
        return tuple(sorted(_open_orders.values(), key=lambda o: o.id, reverse=True))


def open_order_count() -> int:
    with _lock:
        return len(_open_orders)


def history(limit: int = 50) -> tuple[Fill, ...]:
    """Fills, newest first."""
    with _lock:
        return tuple(_history[:limit])


def portfolio_value() -> float:
    """Cash ($MEOW) + mark-to-market of every position at the current price."""
    # Snapshot prices first (SimFeed._lock), then read positions (_lock) — never
    # both at once.
    snapshot = positions()
    feed = get_feed()
    marks = {p.symbol: feed.ticker(p.symbol).price for p in snapshot}
    cash = wallet.balance()
    return float(cash) + sum(p.size * marks[p.symbol] for p in snapshot)


def pnl() -> float:
    """Unrealized P&L: sum of size * (current price - avg cost)."""
    snapshot = positions()
    feed = get_feed()
    marks = {p.symbol: feed.ticker(p.symbol).price for p in snapshot}
    return sum(p.size * (marks[p.symbol] - p.avg_price) for p in snapshot)


def reset() -> None:
    """Clear all state to the empty seed. Used by the test fixture for isolation."""
    global _next_order_id
    with _lock:
        _positions.clear()
        _open_orders.clear()
        _history.clear()
        _next_order_id = 1
