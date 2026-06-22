"""Kraken WebSocket v2 feed — upstream WS → Lucky Cat ``FeedSource`` (#226)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from feed import DEFAULT_SEED, SimFeed, Tick
from feed_adapters._helpers import (
    map_kraken_book,
    map_kraken_ticker,
    map_kraken_trades,
)
from feed_adapters._mapping import KRAKEN_PAIRS, KRAKEN_TO_LC, USER_AGENT

logger = logging.getLogger("lucky_cat.feed.kraken")

_KRAKEN_WS = "wss://ws.kraken.com/v2"
_CONNECT_TIMEOUT_S = 8.0
_PING_INTERVAL_S = 30.0


@dataclass(slots=True)
class _SymbolLive:
    ticker: object
    book: object
    trades: tuple
    event: asyncio.Event = field(default_factory=asyncio.Event)


class KrakenFeed:
    """Live Kraken market data with sim fallback for unmapped house-token pairs."""

    def __init__(self) -> None:
        self._sim = SimFeed(seed=DEFAULT_SEED, tick_interval=1.0)
        self._sim.warm()
        self._lock = threading.Lock()
        self._live: dict[str, _SymbolLive] = {}
        self._started = False
        self._start_ok = False
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> bool:
        if self._started:
            return self._start_ok
        self._started = True
        try:
            import websockets  # noqa: F401
        except ImportError:
            logger.warning("KrakenFeed requires the websockets package.")
            return False
        try:
            await asyncio.wait_for(self._probe_connect(), timeout=_CONNECT_TIMEOUT_S)
        except Exception:
            logger.warning("KrakenFeed could not connect; falling back to sim.", exc_info=True)
            return False
        self._start_ok = True
        self._task = asyncio.create_task(self._run_ws(), name="kraken-feed")
        return True

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _probe_connect(self) -> None:
        import websockets

        pairs = list(KRAKEN_PAIRS.values())
        async with websockets.connect(
            _KRAKEN_WS,
            user_agent_header=USER_AGENT,
            open_timeout=_CONNECT_TIMEOUT_S,
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "method": "subscribe",
                        "params": {"channel": "ticker", "symbol": pairs[:1]},
                    }
                )
            )
            raw = await asyncio.wait_for(ws.recv(), timeout=_CONNECT_TIMEOUT_S)
            msg = json.loads(raw)
            if msg.get("success") is False:
                raise RuntimeError(msg.get("error", "subscribe failed"))

    async def _run_ws(self) -> None:
        import websockets

        pairs = list(KRAKEN_PAIRS.values())
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    _KRAKEN_WS,
                    user_agent_header=USER_AGENT,
                    ping_interval=_PING_INTERVAL_S,
                ) as ws:
                    for channel in ("ticker", "book", "trade"):
                        await ws.send(
                            json.dumps(
                                {
                                    "method": "subscribe",
                                    "params": {
                                        "channel": channel,
                                        "symbol": pairs,
                                        **({"snapshot": True} if channel == "trade" else {}),
                                        **({"depth": 12} if channel == "book" else {}),
                                    },
                                }
                            )
                        )
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        self._handle_message(json.loads(raw))
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._stop.is_set():
                    break
                logger.warning("KrakenFeed disconnected; reconnecting in 3s.", exc_info=True)
                await asyncio.sleep(3.0)

    def _handle_message(self, msg: dict) -> None:
        channel = msg.get("channel")
        if channel not in {"ticker", "book", "trade"}:
            return
        for row in msg.get("data") or []:
            lc = KRAKEN_TO_LC.get(row.get("symbol", ""))
            if lc is None:
                continue
            with self._lock:
                slot = self._live.setdefault(lc, _SymbolLive(None, None, ()))
                if channel == "ticker":
                    slot.ticker = map_kraken_ticker(lc, row)
                elif channel == "book":
                    book_ts = slot.ticker.ts if slot.ticker is not None else time.time()  # type: ignore[union-attr]
                    slot.book = map_kraken_book(
                        lc,
                        row.get("bids") or [],
                        row.get("asks") or [],
                        depth=12,
                        ts=book_ts,
                    )
                elif channel == "trade":
                    existing = list(slot.trades)
                    existing.extend(
                        map_kraken_trades(lc, [row], limit=1),
                    )
                    existing.sort(key=lambda t: t.ts, reverse=True)
                    slot.trades = tuple(existing[:30])
            slot.event.set()

    def _snapshot(self, symbol: str):
        with self._lock:
            slot = self._live.get(symbol)
        if slot and slot.ticker is not None:
            return slot
        return None

    def markets(self):
        return self._sim.markets()

    def has_symbol(self, symbol: str) -> bool:
        return self._sim.has_symbol(symbol)

    @property
    def worker_count(self) -> int:
        return self._sim.worker_count

    @property
    def market_count(self) -> int:
        return self._sim.market_count

    def tick_count(self) -> int:
        return self._sim.tick_count()

    def ticker(self, symbol: str):
        live = self._snapshot(symbol)
        if live and live.ticker is not None:
            return live.ticker
        return self._sim.ticker(symbol)

    def order_book(self, symbol: str, depth: int = 12):
        live = self._snapshot(symbol)
        if live and live.book is not None:
            book = live.book
            return type(book)(
                symbol=book.symbol,
                bids=book.bids[:depth],
                asks=book.asks[:depth],
                ts=book.ts,
            )
        return self._sim.order_book(symbol, depth=depth)

    def trades(self, symbol: str, limit: int = 30):
        live = self._snapshot(symbol)
        if live and live.trades:
            return live.trades[:limit]
        return self._sim.trades(symbol, limit=limit)

    def candles(self, symbol: str, interval: str = "1m", limit: int = 60):
        return self._sim.candles(symbol, interval=interval, limit=limit)

    def consume_depth(self, symbol: str, side: str, size: float) -> None:
        self._sim.consume_depth(symbol, side, size)

    def append_trade(self, symbol: str, side: str, size: float, price: float) -> None:
        self._sim.append_trade(symbol, side, size, price)

    async def subscribe(self, symbol: str) -> AsyncIterator[Tick]:
        if not self._start_ok:
            async for tick in self._sim.subscribe(symbol):
                yield tick
            return
        self._sim._require(symbol)
        while True:
            live = self._snapshot(symbol)
            if live and live.ticker is not None:
                book = live.book if live.book is not None else self._sim.order_book(symbol)
                trades = live.trades if live.trades else self._sim.trades(symbol)
                yield Tick(symbol=symbol, ticker=live.ticker, book=book, trades=trades)
                live.event.clear()
                try:
                    await asyncio.wait_for(live.event.wait(), timeout=2.0)
                except TimeoutError:
                    await asyncio.sleep(0.05)
            else:
                async for tick in self._sim.subscribe(symbol):
                    yield tick
                    break

    def shutdown_sync(self) -> None:
        self._sim.shutdown()
