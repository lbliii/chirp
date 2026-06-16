"""Thread-safe trading store for Lucky Cat — the M2 mutation backend (#225).

Per-visitor state (#285): positions, orders, and fills live in :mod:`session_store`
keyed by browser session. The cash side ($MEOW) is the wallet slice in the same
bucket so buys/sells stay atomic within one session.

Convention: frozen dataclass models, session-scoped state guarded by the
registry lock, and ``reset()`` for test isolation.
"""

import time
from dataclasses import dataclass, replace

import session_store
import wallet
from feed import get_feed

MIN_NOTIONAL_MEOW = 1.0


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


def _known_symbols() -> set[str]:
    return {m.symbol for m in get_feed().markets()}


def validate_order(
    symbol: str,
    side: str,
    kind: str,
    size_raw: str,
    limit_raw: str,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """Validate raw form values, returning ``(errors, parsed)``."""
    errors: dict[str, list[str]] = {}
    parsed: dict[str, object] = {}

    if symbol not in _known_symbols():
        errors.setdefault("symbol", []).append("Pick a market.")
    if side not in ("buy", "sell"):
        errors.setdefault("side", []).append("Choose buy or sell.")
    if kind not in ("market", "limit"):
        errors.setdefault("kind", []).append("Choose market or limit.")

    try:
        size = float(size_raw)
    except ValueError, TypeError:
        size = 0.0
        errors.setdefault("size", []).append("Enter a valid size.")
    else:
        if size <= 0:
            errors.setdefault("size", []).append("Size must be greater than zero.")
    parsed["size"] = size

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
    else:
        held = _position_size(symbol)
        if size > held:
            errors.setdefault("size", []).append(f"You only hold {held:g} {symbol.split('-')[0]}.")

    return errors, parsed


def _position_size(symbol: str) -> float:
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        pos = state.trade.positions.get(symbol)
        return pos.size if pos is not None else 0.0


def try_place_order(
    symbol: str,
    side: str,
    kind: str,
    size: float,
    limit_price: float | None = None,
    *,
    fill_price: float | None = None,
) -> tuple[Order | None, dict[str, list[str]]]:
    """Atomically validate-and-fill an order — concurrency-safe, never raises."""
    if fill_price is None:
        fill_price = limit_price if kind == "limit" else get_feed().ticker(symbol).price
    price = float(fill_price)
    notional = size * price
    cost = round(notional)
    ts = time.time()

    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        if side == "buy":
            spend = max(0, int(cost))
            if spend > state.wallet.balance:
                return None, {
                    "size": [f"Not enough $MEOW. You have {state.wallet.balance}."],
                }
            state.wallet.balance -= spend
        else:
            credit = max(0, int(cost))
            state.wallet.balance += credit

        order_id = state.trade.next_order_id
        state.trade.next_order_id += 1
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
        _apply_fill_locked(state, symbol, side, size, price)
        state.trade.history.insert(0, Fill(order_id, symbol, side, size, price, ts))

    if kind == "market":
        feed = get_feed()
        consume = getattr(feed, "consume_depth", None)
        append = getattr(feed, "append_trade", None)
        if consume is not None and append is not None:
            consume(symbol, side, size)
            append(symbol, side, size, price)

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
    """Fill an order at the current price (M2 always-fill sim) and book it."""
    order, _errors = try_place_order(symbol, side, kind, size, limit_price, fill_price=fill_price)
    if order is None:
        raise ValueError("insufficient balance")
    return order


def _apply_fill_locked(state: session_store.StoreState, symbol: str, side: str, size: float, price: float) -> None:
    """Update the net position for a fill. Caller holds the registry lock."""
    positions = state.trade.positions
    pos = positions.get(symbol)
    cur_size = pos.size if pos is not None else 0.0
    cur_avg = pos.avg_price if pos is not None else 0.0

    if side == "buy":
        new_size = cur_size + size
        new_avg = ((cur_size * cur_avg) + (size * price)) / new_size if new_size else price
    else:
        new_size = cur_size - size
        new_avg = cur_avg

    if new_size <= 1e-9:
        positions.pop(symbol, None)
    elif pos is None:
        positions[symbol] = Position(symbol=symbol, size=new_size, avg_price=new_avg)
    else:
        positions[symbol] = replace(pos, size=new_size, avg_price=new_avg)


def open_limit_order(
    symbol: str,
    side: str,
    size: float,
    limit_price: float,
) -> Order:
    """Book a resting (unfilled) limit order."""
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        order_id = state.trade.next_order_id
        state.trade.next_order_id += 1
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
        state.trade.open_orders[order_id] = order
        return order


def cancel_order(order_id: int) -> Order | None:
    """Flip an open order to ``cancelled``. Returns it, or ``None`` if unknown."""
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        order = state.trade.open_orders.pop(order_id, None)
        if order is None:
            return None
        return replace(order, status="cancelled")


def positions() -> tuple[Position, ...]:
    """Non-zero holdings, stable-sorted by symbol."""
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        return tuple(sorted(state.trade.positions.values(), key=lambda p: p.symbol))


def position(symbol: str) -> Position | None:
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        return state.trade.positions.get(symbol)


def open_orders() -> tuple[Order, ...]:
    """Resting orders, newest first."""
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        return tuple(sorted(state.trade.open_orders.values(), key=lambda o: o.id, reverse=True))


def open_order_count() -> int:
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        return len(state.trade.open_orders)


def history(limit: int = 50) -> tuple[Fill, ...]:
    """Fills, newest first."""
    with session_store.locked(balance_seed=wallet.INITIAL_MEOW) as state:
        return tuple(state.trade.history[:limit])


def portfolio_value() -> float:
    """Cash ($MEOW) + mark-to-market of every position at the current price."""
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
    """Clear every session bucket. Used by the test fixture for isolation."""
    session_store.reset()
