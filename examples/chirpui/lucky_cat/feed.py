"""Market-data boundary for Lucky Cat — ``FeedSource`` protocol + ``SimFeed``.

The framework code never touches an exchange directly. It talks to a
:class:`FeedSource`: a source-agnostic seam exposing a markets list, ticker /
order-book / trade-tape / candle snapshots, a starting portfolio, and an async
``subscribe`` stream the SSE route (#223) consumes.

The shipped default is :class:`SimFeed`: a fully deterministic, dependency-free
price simulator. Given a seed it produces an identical tick sequence, so it
doubles as the test fixture and lets Lucky Cat clone-and-run offline / CI-safe.
Live adapters (Kraken, Coinbase, ...) are out of scope for M1 (#6); this module
only fixes the protocol seam and the sim default.

Determinism + parallelism: each symbol owns an independent, seeded
:class:`random.Random` stream, so the *advance* of one symbol never depends on
the order in which symbols are advanced. That is what lets the per-tick price
update fan out across worker threads (:class:`~concurrent.futures.ThreadPoolExecutor`)
for honest CPU-bound parallel work — the free-threading proof hook for #7 —
*without* perturbing the deterministic sequence. No sleeps are used to fake load.

Pure stdlib only (``random``, ``math``, ``threading``, ``concurrent.futures``,
``asyncio``); importing this module does not re-enable the GIL on a 3.14t build.
"""

import asyncio
import logging
import math
import os
import threading
import zlib
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from random import Random
from typing import Protocol, runtime_checkable

logger = logging.getLogger("lucky_cat.feed")

# Default seed — 0xCA7 ("cat"). Same seed => identical tick sequence.
DEFAULT_SEED = 0xCA7


def _sym_hash(symbol: str) -> int:
    """Process-stable 32-bit digest of a symbol.

    Builtin ``hash(str)`` is salted per process (``PYTHONHASHSEED``), which would
    make the "same seed => identical tick sequence" guarantee false across runs
    and break the CI fixture. ``zlib.crc32`` is stable everywhere, so the master
    seed stays the single source of randomness.
    """
    return zlib.crc32(symbol.encode())


# ---------------------------------------------------------------------------
# Models — frozen dataclasses (slots=True). The same objects flow from the feed
# through the context provider into the templates; no serialization layer.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Market:
    symbol: str
    base: str
    quote: str
    display_name: str


@dataclass(frozen=True, slots=True)
class Ticker:
    symbol: str
    price: float
    change_24h: float
    change_pct_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    ts: float


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True, slots=True)
class OrderBook:
    symbol: str
    bids: tuple[BookLevel, ...]  # descending by price
    asks: tuple[BookLevel, ...]  # ascending by price
    ts: float


@dataclass(frozen=True, slots=True)
class Trade:
    id: int
    symbol: str
    price: float
    size: float
    side: str  # "buy" | "sell"
    ts: float


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ts: float


@dataclass(frozen=True, slots=True)
class Portfolio:
    cash_meow: float
    positions: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class Tick:
    """One fanned-out update bundle yielded by ``subscribe`` per simulated step."""

    symbol: str
    ticker: Ticker
    book: OrderBook
    trades: tuple[Trade, ...]


@runtime_checkable
class FeedSource(Protocol):
    """Source-agnostic market-data boundary.

    Snapshot methods are sync and cheap (safe to call from a context provider /
    page handler). ``subscribe`` is the async stream the SSE route iterates; it
    must be cancellation-safe — a clean stop when the client disconnects.
    """

    def markets(self) -> tuple[Market, ...]:
        """Full market list for the sidebar / landing grid."""
        ...

    def ticker(self, symbol: str) -> Ticker:
        """Current ticker snapshot for ``symbol``."""
        ...

    def order_book(self, symbol: str, depth: int = 12) -> OrderBook:
        """Top-``depth`` order-book snapshot (bids desc, asks asc)."""
        ...

    def trades(self, symbol: str, limit: int = 30) -> tuple[Trade, ...]:
        """Recent-trades tape, newest first."""
        ...

    def candles(self, symbol: str, interval: str = "1m", limit: int = 60) -> tuple[Candle, ...]:
        """OHLC history for ``interval`` (``1m`` / ``1H`` / ``1D`` / ``1W``), oldest first."""
        ...

    def portfolio(self) -> Portfolio:
        """Starting balances. Reserved for the trade-flow issue."""
        ...

    def subscribe(self, symbol: str) -> AsyncIterator[Tick]:
        """Async stream of :class:`Tick` bundles, one per simulated update."""
        ...


# ---------------------------------------------------------------------------
# SimFeed — deterministic server-side price engine.
# ---------------------------------------------------------------------------

# Static market definitions. (symbol, base, quote, display_name, seed_price, daily_vol)
# Everything is priced in the house token $MEOW so the sim is self-contained.
_MARKET_DEFS: tuple[tuple[str, str, str, str, float, float], ...] = (
    ("BTC-MEOW", "BTC", "MEOW", "Bitcoin", 64_000.0, 0.020),
    ("ETH-MEOW", "ETH", "MEOW", "Ether", 3_400.0, 0.028),
    ("SOL-MEOW", "SOL", "MEOW", "Solana", 145.0, 0.045),
    ("DOGE-MEOW", "DOGE", "MEOW", "Dogecoin", 0.16, 0.060),
    ("PAW-MEOW", "PAW", "MEOW", "PawCoin", 8.40, 0.080),
    ("KOBAN-MEOW", "KOBAN", "MEOW", "Koban", 21.00, 0.035),
)

# Timeframe contract for the chart toggle. ``1m`` is the live engine candle ring
# (aggregated from the per-tick walk); the coarser intervals are deterministic
# synthetic OHLC histories generated per (symbol, interval) seed — see
# ``SimFeed._interval_candles``. ``seconds`` is the nominal candle period and
# ``count`` the number of buckets the chart shows; ``vol`` scales the per-bucket
# walk so a 1W candle moves more than a 1H one. Order is the toggle's display
# order. ``1m`` is intentionally absent here (it reads the live ring directly).
DEFAULT_INTERVAL = "1H"
_INTERVAL_DEFS: dict[str, tuple[int, int, float]] = {
    # interval: (seconds_per_bucket, bucket_count, per-bucket vol multiplier)
    "1H": (3_600, 60, 0.45),
    "1D": (86_400, 48, 0.90),
    "1W": (604_800, 52, 1.6),
}
# Public, ordered timeframe list for the chart toggle (1m first, then coarser).
INTERVALS: tuple[str, ...] = ("1m", *(_INTERVAL_DEFS.keys()))


@dataclass(slots=True)
class _SymbolState:
    """Per-symbol mutable simulation state. Each owns an independent PRNG so the
    advance of one symbol is order-independent of the others (deterministic under
    thread fan-out)."""

    market: Market
    rng: Random
    anchor: float  # mean-reversion target ("fair value")
    price: float
    open_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    candle_open: float
    candle_high: float
    candle_low: float
    candle_volume: float
    trades: list[Trade]
    candles: list[Candle]
    next_trade_id: int
    step: int


class SimFeed:
    """Deterministic, dependency-free market simulator.

    ``SimFeed(seed)`` with the same seed yields an identical tick sequence. The
    engine is a bounded geometric random walk with mean-reversion toward a
    per-symbol anchor (so prices wander but never run away), plus a synthetic
    order book and trade tape derived from the current price.
    """

    # Per-step mean-reversion pull toward the anchor and walk volatility scale.
    _REVERSION = 0.015
    _VOL_SCALE = 0.55
    _DEPTH = 24  # full book depth maintained; ``order_book`` slices to ``depth``
    _TAPE_MAX = 60  # recent-trades ring length
    _CANDLE_STEPS = 12  # simulated steps per candle
    _CANDLE_MAX = 120
    # Steps to advance on build/reset so first-paint snapshots (tape, candles,
    # 24h stats) are populated. > _CANDLE_STEPS so at least one candle closes.
    _WARM_STEPS = 24

    def __init__(self, seed: int = DEFAULT_SEED, *, tick_interval: float = 1.0) -> None:
        self._seed = seed
        # Seconds between ``subscribe`` ticks (SSE cadence). This is presentation
        # pacing, *not* part of the deterministic engine — the tick *sequence* is
        # identical regardless of interval, so tests pass ``tick_interval=0`` to
        # exercise the engine at full speed.
        self._tick_interval = tick_interval
        self._lock = threading.Lock()
        # Worker pool for the per-tick fan-out. Bounded to the symbol count so
        # CPU-bound price work runs in parallel under free-threading.
        self._pool = ThreadPoolExecutor(
            max_workers=max(2, len(_MARKET_DEFS)),
            thread_name_prefix="luckycat-tick",
        )
        self._states: dict[str, _SymbolState] = {}
        # Observability-only tick counter (#227 free-threading proof). Bumped once
        # per *symbol-advance* inside _advance_symbol, so it counts genuine
        # parallel increments across the worker pool. It is NEVER read by the
        # price engine, so it cannot perturb the deterministic tick sequence —
        # guarded by its own lock to keep the hot path off self._lock.
        self._tick_lock = threading.Lock()
        self._tick_count = 0
        self._init_states(seed)

    # -- setup / reset ----------------------------------------------------

    def _init_states(self, seed: int) -> None:
        states: dict[str, _SymbolState] = {}
        for symbol, base, quote, name, price0, _vol in _MARKET_DEFS:
            market = Market(symbol=symbol, base=base, quote=quote, display_name=name)
            # Derive a stable per-symbol seed from the master seed + symbol so
            # streams are independent yet fully reproducible.
            sub_seed = (seed * 1_000_003) ^ (_sym_hash(symbol) & 0xFFFF_FFFF)
            rng = Random(sub_seed)
            states[symbol] = _SymbolState(
                market=market,
                rng=rng,
                anchor=price0,
                price=price0,
                open_24h=price0,
                high_24h=price0,
                low_24h=price0,
                volume_24h=0.0,
                candle_open=price0,
                candle_high=price0,
                candle_low=price0,
                candle_volume=0.0,
                trades=[],
                candles=[],
                next_trade_id=1,
                step=0,
            )
        self._states = states

    def reset(self, seed: int | None = None) -> None:
        """Reset all symbols to seed state (step 0, empty tape). Used by tests
        for isolation. This is a pure restore — it does NOT warm, so a fresh
        ``subscribe`` after reset replays the exact seed sequence. Callers that
        want a populated first paint (e.g. the running app, conftest) call
        :meth:`warm` explicitly afterwards."""
        with self._lock:
            self._seed = self._seed if seed is None else seed
            self._init_states(self._seed)
        # Observability counter is independent of the deterministic engine, so it
        # lives under its own lock and resets to zero for clean test isolation.
        with self._tick_lock:
            self._tick_count = 0

    def warm(self, steps: int | None = None) -> None:
        """Advance every symbol a fixed number of steps so snapshot reads
        (ticker / order book / trade tape / candles) are immediately meaningful
        on the first page paint, before any ``subscribe`` tick has run.

        Deterministic: a fixed ``steps`` from seed state always yields the same
        warmed snapshot, so this does not perturb the reproducibility guarantee.
        """
        with self._lock:
            self._warm_locked(steps)

    def _warm_locked(self, steps: int | None = None) -> None:
        n = self._WARM_STEPS if steps is None else steps
        for _ in range(n):
            self._advance_all()

    # -- price engine -----------------------------------------------------

    def _vol_for(self, symbol: str) -> float:
        for sym, _b, _q, _n, _p, vol in _MARKET_DEFS:
            if sym == symbol:
                return vol
        return 0.03

    def _advance_symbol(self, symbol: str) -> Tick:
        """Advance one symbol by a single step and return its update bundle.

        Honest CPU-bound work — no sleeps. Each symbol uses only its own PRNG
        and its own state slice, so this is safe to run concurrently across
        threads and the result is independent of fan-out order.
        """
        st = self._states[symbol]
        vol = self._vol_for(symbol)
        st.step += 1
        ts = float(st.step)

        # Free-threading proof (#227): count this symbol-advance. Multiple worker
        # threads hit this concurrently under a 3.14t build, so the counter is an
        # honest measure of parallel CPU work. Its own lock keeps it off the
        # engine's self._lock and it is read only by the FT panel, never here.
        with self._tick_lock:
            self._tick_count += 1

        # Geometric random walk with mean-reversion toward the anchor.
        shock = st.rng.gauss(0.0, 1.0) * vol * self._VOL_SCALE
        reversion = self._REVERSION * math.log(st.anchor / st.price) if st.price > 0 else 0.0
        log_return = reversion + shock
        new_price = st.price * math.exp(log_return)
        # Clamp to a sane band around the anchor so the sim never degenerates.
        lo, hi = st.anchor * 0.40, st.anchor * 2.50
        new_price = min(max(new_price, lo), hi)
        st.price = new_price

        # 24h rolling stats.
        st.high_24h = max(st.high_24h, new_price)
        st.low_24h = min(st.low_24h, new_price)

        # Synthetic trade(s) for this step — drives the tape and volume.
        n_trades = 1 + int(abs(st.rng.gauss(0.0, 1.0)))
        step_trades: list[Trade] = []
        for _ in range(n_trades):
            side = "buy" if st.rng.random() < 0.5 else "sell"
            size = round(
                abs(st.rng.gauss(0.0, 1.0)) * self._size_unit(new_price)
                + self._size_unit(new_price) * 0.1,
                6,
            )
            trade = Trade(
                id=st.next_trade_id,
                symbol=symbol,
                price=round(new_price, self._price_dp(new_price)),
                size=size,
                side=side,
                ts=ts,
            )
            st.next_trade_id += 1
            step_trades.append(trade)
            st.volume_24h += size
            st.candle_volume += size

        # Newest-first tape, bounded ring.
        st.trades[:0] = reversed(step_trades)
        del st.trades[self._TAPE_MAX :]

        # Candle aggregation.
        st.candle_high = max(st.candle_high, new_price)
        st.candle_low = min(st.candle_low, new_price)
        if st.step % self._CANDLE_STEPS == 0:
            st.candles.append(
                Candle(
                    symbol=symbol,
                    open=round(st.candle_open, self._price_dp(new_price)),
                    high=round(st.candle_high, self._price_dp(new_price)),
                    low=round(st.candle_low, self._price_dp(new_price)),
                    close=round(new_price, self._price_dp(new_price)),
                    volume=round(st.candle_volume, 6),
                    ts=ts,
                )
            )
            del st.candles[: max(0, len(st.candles) - self._CANDLE_MAX)]
            st.candle_open = new_price
            st.candle_high = new_price
            st.candle_low = new_price
            st.candle_volume = 0.0

        return Tick(
            symbol=symbol,
            ticker=self._ticker_locked(st),
            book=self._book_locked(st, self._DEPTH),
            trades=tuple(st.trades),
        )

    def _advance_all(self) -> dict[str, Tick]:
        """Advance every symbol one step, fanned out across worker threads.

        The fan-out is honest CPU parallelism; determinism is preserved because
        each task only touches its own symbol's PRNG/state slice.
        """
        symbols = list(self._states)
        results = list(self._pool.map(self._advance_symbol, symbols))
        return dict(zip(symbols, results, strict=True))

    # -- derived snapshots (assume caller holds the relevant invariants) ---

    @staticmethod
    def _price_dp(price: float) -> int:
        if price >= 1000:
            return 2
        if price >= 1:
            return 4
        return 6

    @staticmethod
    def _size_unit(price: float) -> float:
        # Larger notional markets trade in smaller unit sizes.
        if price >= 1000:
            return 0.05
        if price >= 1:
            return 5.0
        return 500.0

    def _ticker_locked(self, st: _SymbolState) -> Ticker:
        change = st.price - st.open_24h
        pct = (change / st.open_24h * 100.0) if st.open_24h else 0.0
        dp = self._price_dp(st.price)
        return Ticker(
            symbol=st.market.symbol,
            price=round(st.price, dp),
            change_24h=round(change, dp),
            change_pct_24h=round(pct, 2),
            high_24h=round(st.high_24h, dp),
            low_24h=round(st.low_24h, dp),
            volume_24h=round(st.volume_24h, 4),
            ts=float(st.step),
        )

    def _book_locked(self, st: _SymbolState, depth: int) -> OrderBook:
        dp = self._price_dp(st.price)
        spread = max(st.price * 0.0004, 10.0**-dp)
        mid = st.price
        bids: list[BookLevel] = []
        asks: list[BookLevel] = []
        unit = self._size_unit(st.price)
        # Deterministic synthetic ladder seeded off the symbol's PRNG state via a
        # fresh local generator keyed on the step (so the book is reproducible).
        ladder_rng = Random((_sym_hash(st.market.symbol) & 0xFFFF) ^ (st.step * 2_654_435_761))
        for i in range(1, self._DEPTH + 1):
            bid_price = mid - spread * i
            ask_price = mid + spread * i
            depth_decay = math.exp(-0.08 * i)
            bid_size = round((unit * 4.0 * depth_decay) * (0.6 + ladder_rng.random()), 6)
            ask_size = round((unit * 4.0 * depth_decay) * (0.6 + ladder_rng.random()), 6)
            bids.append(BookLevel(price=round(bid_price, dp), size=bid_size))
            asks.append(BookLevel(price=round(ask_price, dp), size=ask_size))
        return OrderBook(
            symbol=st.market.symbol,
            bids=tuple(bids[:depth]),
            asks=tuple(asks[:depth]),
            ts=float(st.step),
        )

    # -- FeedSource protocol ----------------------------------------------

    def markets(self) -> tuple[Market, ...]:
        return tuple(st.market for st in self._states.values())

    # -- free-threading observability (#227 Part A) -----------------------

    @property
    def worker_count(self) -> int:
        """Size of the per-tick fan-out pool — the parallel-work width.

        Exposed so the FT panel template never reaches into the private
        ``_pool``; it is the number of OS threads the price engine fans across.
        """
        return self._pool._max_workers

    @property
    def market_count(self) -> int:
        """Number of markets advanced per tick (one CPU task each)."""
        return len(self._states)

    def tick_count(self) -> int:
        """Total symbol-advances since process start / last reset.

        Read by the FT panel to derive a ticks/sec rate; observability only.
        """
        with self._tick_lock:
            return self._tick_count

    def _require(self, symbol: str) -> _SymbolState:
        st = self._states.get(symbol)
        if st is None:
            raise KeyError(symbol)
        return st

    def ticker(self, symbol: str) -> Ticker:
        with self._lock:
            return self._ticker_locked(self._require(symbol))

    def order_book(self, symbol: str, depth: int = 12) -> OrderBook:
        with self._lock:
            return self._book_locked(self._require(symbol), depth)

    def trades(self, symbol: str, limit: int = 30) -> tuple[Trade, ...]:
        with self._lock:
            st = self._require(symbol)
            return tuple(st.trades[:limit])

    def candles(self, symbol: str, interval: str = "1m", limit: int = 60) -> tuple[Candle, ...]:
        """OHLC history for ``interval``, oldest first (bounded to ``limit``).

        ``1m`` returns the live engine candle ring (aggregated from the per-tick
        walk). The coarser intervals (``1H`` / ``1D`` / ``1W``) return a
        deterministic synthetic OHLC history generated per ``(symbol, interval)``
        seed by :meth:`_interval_candles`: same seed + interval => identical
        series, and the series ends at the symbol's current live price so the
        chart agrees with the live ticker. An unknown interval falls back to
        ``1m`` (the live ring) rather than raising — the route already clamps to
        :data:`INTERVALS`, so this is just a defensive floor.
        """
        with self._lock:
            st = self._require(symbol)
            if interval not in _INTERVAL_DEFS:
                return tuple(st.candles[-limit:])
            return self._interval_candles(st, interval, limit)

    def _interval_candles(self, st: _SymbolState, interval: str, limit: int) -> tuple[Candle, ...]:
        """Deterministic synthetic OHLC history for a coarse ``interval``.

        Caller holds ``self._lock``. The walk is a fresh, seeded mean-reverting
        random walk keyed on ``(symbol, interval)`` so it is fully reproducible
        and independent of the live tick sequence (reading it never perturbs the
        engine). The walk *shape* is then affine-mapped so its FIRST close lands
        on the symbol's 24h open and its LAST close on the current live price.
        That pins both endpoints exactly, so the chart's first-vs-last direction
        ALWAYS agrees with the 24h delta pill (jade up / red down) — the focal
        chart can never contradict the headline number. The per-bucket ``vol``
        widens with the timeframe so a 1W candle ranges more than a 1H one.
        ``ts`` is the bucket index (oldest=0) — the geometry helper only needs
        the close ordering.
        """
        seconds, count, vol_mult = _INTERVAL_DEFS[interval]
        n = min(count, max(2, limit))
        symbol = st.market.symbol
        dp = self._price_dp(st.price)
        vol = self._vol_for(symbol) * vol_mult
        # Per-(symbol, interval) seed — stable across runs, distinct per timeframe.
        seed = (_sym_hash(symbol) & 0xFFFF_FFFF) ^ (_sym_hash(interval) * 2_654_435_761)
        rng = Random(seed & 0xFFFF_FFFF_FFFF_FFFF)
        anchor = st.anchor
        # Walk forward from the anchor to get a reproducible *shape*.
        raw: list[float] = []
        price = anchor
        for _ in range(n):
            shock = rng.gauss(0.0, 1.0) * vol
            reversion = self._REVERSION * math.log(anchor / price) if price > 0 else 0.0
            price = price * math.exp(reversion + shock)
            price = min(max(price, anchor * 0.40), anchor * 2.50)
            raw.append(price)
        # Affine-map the shape so closes[0] == open_24h and closes[-1] == live
        # price. Endpoints are pinned exactly, so the direction equals the 24h
        # delta's sign; interior buckets interpolate the residual shape linearly.
        start = st.open_24h
        end = st.price
        raw_first, raw_last = raw[0], raw[-1]
        raw_span = raw_last - raw_first
        closes: list[float] = []
        for i, r in enumerate(raw):
            base = start + (end - start) * (i / (n - 1)) if n > 1 else end
            # Add the de-trended residual of the raw walk (scaled to the price
            # band) so the line keeps its wiggle without dragging the endpoints.
            residual = (r - (raw_first + raw_span * (i / (n - 1)))) if (n > 1 and raw_span) else 0.0
            closes.append(max(base + residual, anchor * 0.40))
        # Force the exact endpoints (residual is ~0 there but pin to be safe).
        closes[0] = start
        closes[-1] = end
        candles: list[Candle] = []
        prev_close = closes[0]
        for i, close in enumerate(closes):
            open_ = prev_close
            # Intrabar high/low straddle the open/close by a deterministic wick.
            wick = abs(rng.gauss(0.0, 1.0)) * close * vol * 0.5
            hi = max(open_, close) + wick
            lo = max(min(open_, close) - wick, anchor * 0.40)
            vol_size = round(abs(rng.gauss(0.0, 1.0)) * self._size_unit(close) * 8.0, 6)
            candles.append(
                Candle(
                    symbol=symbol,
                    open=round(open_, dp),
                    high=round(hi, dp),
                    low=round(lo, dp),
                    close=round(close, dp),
                    volume=vol_size,
                    ts=float(i * seconds),
                )
            )
            prev_close = close
        return tuple(candles)

    def portfolio(self) -> Portfolio:
        # Starting balances — reserved for the trade-flow issue.
        return Portfolio(
            cash_meow=1_000_000.0,
            positions=(
                ("BTC", 0.0),
                ("ETH", 0.0),
                ("SOL", 0.0),
            ),
        )

    def has_symbol(self, symbol: str) -> bool:
        return symbol in self._states

    async def subscribe(self, symbol: str) -> AsyncIterator[Tick]:
        """Yield a :class:`Tick` for ``symbol`` per simulated step.

        Cancellation-safe: the loop only awaits (``run_in_executor`` /
        ``asyncio.sleep``), so a client disconnect cancels the consuming task and
        the ``CancelledError`` propagates out of the generator cleanly — no
        partial state is left mid-step. The CPU work runs in the thread pool; only
        ``symbol``'s tick is surfaced even though every symbol advances together
        (keeps the cross-page ticker strip coherent).
        """
        self._require(symbol)
        loop = asyncio.get_running_loop()
        while True:
            # Advance every symbol (fan-out happens inside _advance_all),
            # off the event loop so streaming stays responsive.
            ticks = await loop.run_in_executor(None, self._advance_all_locked)
            yield ticks[symbol]
            # Pace the stream. This is cadence, not fake CPU load. tick_interval=0
            # (tests) still yields control so cancellation stays responsive.
            await asyncio.sleep(self._tick_interval)

    def _advance_all_locked(self) -> dict[str, Tick]:
        with self._lock:
            return self._advance_all()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# Source selector — LUCKY_CAT_FEED (default "sim"). Cached singleton.
# ---------------------------------------------------------------------------

_feed_lock = threading.Lock()
_feed: SimFeed | None = None


def _build_feed() -> SimFeed:
    source = os.environ.get("LUCKY_CAT_FEED", "sim").strip().lower()
    if source != "sim":
        # Live adapters are out of scope for M1 (#6). Anything else is unknown
        # or unreachable: fall back to the deterministic sim with a logged
        # warning.
        logger.warning(
            "LUCKY_CAT_FEED=%r is not available (live adapters are out of scope for M1); "
            "falling back to the deterministic SimFeed.",
            source,
        )
    feed = SimFeed(seed=DEFAULT_SEED)
    # Warm so the first page paint shows a populated tape / candles / 24h stats
    # instead of empty placeholders. Deterministic (fixed step count).
    feed.warm()
    return feed


def get_feed() -> FeedSource:
    """Return the process-wide cached feed selected by ``LUCKY_CAT_FEED``."""
    global _feed
    if _feed is None:
        with _feed_lock:
            if _feed is None:
                _feed = _build_feed()
    return _feed


def reset() -> None:
    """Reset the cached app feed to seed state, then re-warm. Used by tests /
    conftest for isolation. Re-warming mirrors :func:`_build_feed` so every
    test sees the same populated first-paint snapshots the running app shows
    (instance ``SimFeed.reset`` stays a pure restore for determinism tests)."""
    global _feed
    with _feed_lock:
        if _feed is None:
            _feed = _build_feed()
        else:
            _feed.reset()
            _feed.warm()
