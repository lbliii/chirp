"""CoinGecko REST poll feed — keyless price/ticker with sim book/trades (#226)."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import os
import threading
import time
from collections.abc import AsyncIterator

import httpx
from feed import DEFAULT_SEED, SimFeed, Tick
from feed_adapters._helpers import synthetic_book, ticker_from_last
from feed_adapters._mapping import COINGECKO_IDS, USER_AGENT

logger = logging.getLogger("lucky_cat.feed.coingecko")

_BASE = "https://api.coingecko.com/api/v3"
_POLL_S = 15.0
_CONNECT_TIMEOUT_S = 8.0

_client_var: contextvars.ContextVar[httpx.AsyncClient | None] = contextvars.ContextVar(
    "coingecko_client",
    default=None,
)


class CoinGeckoFeed:
    """Poll CoinGecko for live spot prices; synthetic L2/tape from the sim seam."""

    def __init__(self) -> None:
        self._sim = SimFeed(seed=DEFAULT_SEED, tick_interval=1.0)
        self._sim.warm()
        self._lock = threading.Lock()
        self._tickers: dict[str, object] = {}
        self._started = False
        self._start_ok = False
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._events: dict[str, asyncio.Event] = {}

    async def start(self) -> bool:
        if self._started:
            return self._start_ok
        self._started = True
        client = httpx.AsyncClient(
            base_url=_BASE,
            headers=self._headers(),
            timeout=_CONNECT_TIMEOUT_S,
        )
        _client_var.set(client)
        try:
            await self._refresh_once(client)
        except Exception:
            logger.warning(
                "CoinGeckoFeed could not reach the API; falling back to sim.", exc_info=True
            )
            await client.aclose()
            _client_var.set(None)
            return False
        self._start_ok = True
        self._task = asyncio.create_task(self._poll_loop(client), name="coingecko-feed")
        return True

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        client = _client_var.get()
        if client is not None:
            await client.aclose()
            _client_var.set(None)

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        key = os.environ.get("COINGECKO_DEMO_API_KEY", "").strip()
        if key:
            headers["x-cg-demo-api-key"] = key
        return headers

    async def _poll_loop(self, client: httpx.AsyncClient) -> None:
        while not self._stop.is_set():
            try:
                await self._refresh_once(client)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("CoinGecko poll failed; retrying.", exc_info=True)
            await asyncio.sleep(_POLL_S)

    async def _refresh_once(self, client: httpx.AsyncClient) -> None:
        ids = ",".join(dict.fromkeys(COINGECKO_IDS.values()))
        resp = await client.get(
            "/simple/price",
            params={
                "ids": ids,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        now = time.time()
        for symbol, coin_id in COINGECKO_IDS.items():
            row = payload.get(coin_id)
            if not row:
                continue
            last = float(row.get("usd", 0.0))
            if last <= 0:
                continue
            ticker = ticker_from_last(
                symbol,
                last=last,
                change_pct=float(row.get("usd_24h_change") or 0.0),
                ts=now,
            )
            with self._lock:
                self._tickers[symbol] = ticker
                self._events.setdefault(symbol, asyncio.Event()).set()

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
        with self._lock:
            live = self._tickers.get(symbol)
        if live is not None:
            return live
        return self._sim.ticker(symbol)

    def order_book(self, symbol: str, depth: int = 12):
        t = self.ticker(symbol)
        return synthetic_book(symbol, t.price, depth=depth, ts=t.ts)

    def trades(self, symbol: str, limit: int = 30):
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
        event = self._events.setdefault(symbol, asyncio.Event())
        while True:
            t = self.ticker(symbol)
            book = self.order_book(symbol)
            trades = self.trades(symbol)
            yield Tick(symbol=symbol, ticker=t, book=book, trades=trades)
            event.clear()
            try:
                await asyncio.wait_for(event.wait(), timeout=_POLL_S)
            except TimeoutError:
                await asyncio.sleep(0.05)

    def shutdown_sync(self) -> None:
        self._sim.shutdown()
