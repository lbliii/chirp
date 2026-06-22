"""mempool.space WebSocket feed — on-chain panel + sim market seam (#226)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from feed import DEFAULT_SEED, SimFeed, Tick
from feed_adapters._mapping import USER_AGENT

logger = logging.getLogger("lucky_cat.feed.mempool")

_MEMPOOL_WS = "wss://mempool.space/api/v1/ws"
_CONNECT_TIMEOUT_S = 8.0


@dataclass(frozen=True, slots=True)
class ChainSnapshot:
    """Live Bitcoin chain stats for the on-chain panel."""

    fastest_fee: int
    half_hour_fee: int
    hour_fee: int
    mempool_txs: int
    mempool_vbytes: int
    block_height: int | None
    block_tx_count: int | None
    updated_at: float


class MempoolFeed:
    """Sim-backed ``FeedSource`` plus a live mempool.space on-chain panel."""

    def __init__(self) -> None:
        self._sim = SimFeed(seed=DEFAULT_SEED, tick_interval=1.0)
        self._sim.warm()
        self._lock = threading.Lock()
        self._chain: ChainSnapshot | None = None
        self._event = asyncio.Event()
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
            logger.warning("MempoolFeed requires the websockets package.")
            return False
        try:
            await asyncio.wait_for(self._probe_connect(), timeout=_CONNECT_TIMEOUT_S)
        except Exception:
            logger.warning("MempoolFeed could not connect; falling back to sim.", exc_info=True)
            return False
        self._start_ok = True
        self._task = asyncio.create_task(self._run_ws(), name="mempool-feed")
        return True

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _probe_connect(self) -> None:
        import websockets

        async with websockets.connect(
            _MEMPOOL_WS,
            user_agent_header=USER_AGENT,
            open_timeout=_CONNECT_TIMEOUT_S,
        ) as ws:
            await ws.send(json.dumps({"action": "want", "data": ["stats"]}))
            raw = await asyncio.wait_for(ws.recv(), timeout=_CONNECT_TIMEOUT_S)
            msg = json.loads(raw)
            if "fees" not in msg and "mempoolInfo" not in msg:
                raise RuntimeError("unexpected mempool handshake payload")

    async def _run_ws(self) -> None:
        import websockets

        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    _MEMPOOL_WS,
                    user_agent_header=USER_AGENT,
                    ping_interval=30,
                ) as ws:
                    await ws.send(
                        json.dumps(
                            {"action": "want", "data": ["stats", "mempool-blocks", "blocks"]}
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
                logger.warning("MempoolFeed disconnected; reconnecting in 3s.", exc_info=True)
                await asyncio.sleep(3.0)

    def _handle_message(self, msg: dict) -> None:
        fees = msg.get("fees") or {}
        info = msg.get("mempoolInfo") or {}
        block = msg.get("block") or {}
        if not fees and not info and not block:
            return
        snap = ChainSnapshot(
            fastest_fee=int(fees.get("fastestFee") or 0),
            half_hour_fee=int(fees.get("halfHourFee") or 0),
            hour_fee=int(fees.get("hourFee") or 0),
            mempool_txs=int(info.get("size") or 0),
            mempool_vbytes=int(info.get("bytes") or 0) // 4 if info.get("bytes") else 0,
            block_height=int(block.get("height")) if block.get("height") is not None else None,
            block_tx_count=int(block.get("tx_count"))
            if block.get("tx_count") is not None
            else None,
            updated_at=time.time(),
        )
        with self._lock:
            self._chain = snap
        self._event.set()

    def chain_snapshot(self) -> ChainSnapshot | None:
        with self._lock:
            return self._chain

    async def watch_chain(self) -> AsyncIterator[ChainSnapshot]:
        self._require_started()
        while True:
            snap = self.chain_snapshot()
            if snap is not None:
                yield snap
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=30.0)
            except TimeoutError:
                await asyncio.sleep(1.0)

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
        return self._sim.ticker(symbol)

    def order_book(self, symbol: str, depth: int = 12):
        return self._sim.order_book(symbol, depth=depth)

    def trades(self, symbol: str, limit: int = 30):
        return self._sim.trades(symbol, limit=limit)

    def candles(self, symbol: str, interval: str = "1m", limit: int = 60):
        return self._sim.candles(symbol, interval=interval, limit=limit)

    def consume_depth(self, symbol: str, side: str, size: float) -> None:
        self._sim.consume_depth(symbol, side, size)

    def append_trade(self, symbol: str, side: str, size: float, price: float) -> None:
        self._sim.append_trade(symbol, side, size, price)

    async def subscribe(self, symbol: str) -> AsyncIterator[Tick]:
        async for tick in self._sim.subscribe(symbol):
            yield tick

    def _require_started(self) -> None:
        if not self._start_ok:
            raise RuntimeError("MempoolFeed.start() must succeed before watch_chain()")

    def shutdown_sync(self) -> None:
        self._sim.shutdown()
