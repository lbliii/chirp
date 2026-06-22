"""Shared helpers for live feed adapters."""

from __future__ import annotations

import math
import time
from datetime import datetime

from feed import BookLevel, Candle, OrderBook, Ticker, Trade


def price_dp(price: float) -> int:
    if price >= 1000:
        return 2
    if price >= 1:
        return 4
    return 6


def parse_iso_ts(raw: str | None) -> float:
    if not raw:
        return time.time()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return time.time()


def ticker_from_last(
    symbol: str,
    *,
    last: float,
    change_pct: float = 0.0,
    high: float | None = None,
    low: float | None = None,
    volume: float = 0.0,
    ts: float | None = None,
) -> Ticker:
    dp = price_dp(last)
    open_ = last / (1.0 + change_pct / 100.0) if change_pct else last
    change = last - open_
    return Ticker(
        symbol=symbol,
        price=round(last, dp),
        change_24h=round(change, dp),
        change_pct_24h=round(change_pct, 2),
        high_24h=round(high if high is not None else max(last, open_), dp),
        low_24h=round(low if low is not None else min(last, open_), dp),
        volume_24h=round(volume, 4),
        ts=float(ts if ts is not None else time.time()),
    )


def synthetic_book(
    symbol: str, mid: float, *, depth: int = 12, ts: float | None = None
) -> OrderBook:
    """A tight synthetic ladder around ``mid`` when upstream has no L2 feed."""
    dp = price_dp(mid)
    spread = max(mid * 0.0004, 10.0**-dp)
    unit = 0.05 if mid >= 1000 else (5.0 if mid >= 1 else 500.0)
    bids: list[BookLevel] = []
    asks: list[BookLevel] = []
    for i in range(1, depth + 1):
        decay = math.exp(-0.08 * i)
        size = round(unit * 4.0 * decay, 6)
        bids.append(BookLevel(price=round(mid - spread * i, dp), size=size))
        asks.append(BookLevel(price=round(mid + spread * i, dp), size=size))
    return OrderBook(
        symbol=symbol,
        bids=tuple(bids),
        asks=tuple(asks),
        ts=float(ts if ts is not None else time.time()),
    )


def empty_trades() -> tuple[Trade, ...]:
    return ()


def map_kraken_book(symbol: str, bids: list, asks: list, *, depth: int, ts: float) -> OrderBook:
    def levels(raw: list, *, reverse: bool) -> tuple[BookLevel, ...]:
        out = [
            BookLevel(
                price=round(float(row["price"]), price_dp(float(row["price"]))),
                size=float(row["qty"]),
            )
            for row in raw[:depth]
        ]
        if reverse:
            out.sort(key=lambda lvl: lvl.price, reverse=True)
        else:
            out.sort(key=lambda lvl: lvl.price)
        return tuple(out)

    return OrderBook(
        symbol=symbol,
        bids=levels(bids, reverse=True),
        asks=levels(asks, reverse=False),
        ts=ts,
    )


def map_kraken_trades(symbol: str, rows: list, *, limit: int = 30) -> tuple[Trade, ...]:
    out: list[Trade] = []
    for row in reversed(rows[-limit:]):
        price = float(row["price"])
        out.append(
            Trade(
                id=int(row["trade_id"]),
                symbol=symbol,
                price=round(price, price_dp(price)),
                size=float(row["qty"]),
                side=str(row["side"]),
                ts=parse_iso_ts(row.get("timestamp")),
            )
        )
    out.sort(key=lambda t: t.ts, reverse=True)
    return tuple(out)


def map_kraken_ticker(symbol: str, row: dict) -> Ticker:
    last = float(row["last"])
    return Ticker(
        symbol=symbol,
        price=round(last, price_dp(last)),
        change_24h=round(float(row.get("change", 0.0)), price_dp(last)),
        change_pct_24h=round(float(row.get("change_pct", 0.0)), 2),
        high_24h=round(float(row.get("high", last)), price_dp(last)),
        low_24h=round(float(row.get("low", last)), price_dp(last)),
        volume_24h=round(float(row.get("volume", 0.0)), 4),
        ts=parse_iso_ts(row.get("timestamp")),
    )


def candles_from_closes(symbol: str, closes: tuple[float, ...]) -> tuple[Candle, ...]:
    if not closes:
        return ()
    candles: list[Candle] = []
    for i, close in enumerate(closes):
        open_ = closes[i - 1] if i else close
        hi = max(open_, close)
        lo = min(open_, close)
        dp = price_dp(close)
        candles.append(
            Candle(
                symbol=symbol,
                open=round(open_, dp),
                high=round(hi, dp),
                low=round(lo, dp),
                close=round(close, dp),
                volume=0.0,
                ts=float(i),
            )
        )
    return tuple(candles)
