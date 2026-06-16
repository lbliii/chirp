"""DOMAIN — market-data boundary for Lucky Cat.

The ``FeedSource`` protocol and the shipped ``SimFeed`` implementation: a
source-agnostic seam between the CHIRP wiring in ``app.py`` and the simulated
exchange. Framework code never touches an exchange directly — routes and pages
call ``get_feed()`` for snapshots or ``subscribe`` to the async tick stream that
SSE routes consume.

The default ``SimFeed`` is fully deterministic (same seed → identical tick
sequence), dependency-free, and doubles as the test fixture so Lucky Cat runs
offline and CI-safe with zero external services. Live adapters (Kraken, Coinbase,
…) are out of scope; only the protocol seam and the sim ship.

Determinism + parallelism: each symbol owns an independent, seeded
:class:`random.Random` stream, so the *advance* of one symbol never depends on
the order in which symbols are advanced. That is what lets the per-tick price
update fan out across worker threads (:class:`~concurrent.futures.ThreadPoolExecutor`)
for honest CPU-bound parallel work without perturbing the deterministic
sequence. No sleeps are used to fake load.

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

    def subscribe(self, symbol: str) -> AsyncIterator[Tick]:
        """Async stream of :class:`Tick` bundles, one per simulated update."""
        ...


# ---------------------------------------------------------------------------
# SimFeed — deterministic server-side price engine.
# ---------------------------------------------------------------------------

# Static market definitions. (symbol, base, quote, display_name, seed_price, daily_vol)
# Everything is priced in the house token $MEOW so the sim is self-contained.
_MarketDef = tuple[str, str, str, str, float, float]
_MARKET_DEFS: tuple[_MarketDef, ...] = (
    ("BTC-MEOW", "BTC", "MEOW", "Bitcoin", 64_000.0, 0.020),
    ("ETH-MEOW", "ETH", "MEOW", "Ether", 3_400.0, 0.028),
    ("SOL-MEOW", "SOL", "MEOW", "Solana", 145.0, 0.045),
    ("DOGE-MEOW", "DOGE", "MEOW", "Dogecoin", 0.16, 0.060),
    ("PAW-MEOW", "PAW", "MEOW", "PawCoin", 8.40, 0.080),
    ("KOBAN-MEOW", "KOBAN", "MEOW", "Koban", 21.00, 0.035),
)

# Env var that grows the catalog to N markets for scale demos. Unset or
# N <= len(_MARKET_DEFS) keeps the shipped 6 verbatim, so the determinism golden
# (test_feed_determinism.py, seed 0xCA7) stays green by default.
_CATALOG_ENV = "LUCKY_CAT_CATALOG"
# Hard ceiling on the worker fan-out. The price engine is one CPU task per
# symbol; a 500-coin catalog must NOT spawn 500 OS threads. Bound the pool so the
# fan-out stays a sane width regardless of catalog size (default 6 -> 6 workers,
# unchanged). See SimFeed.__init__.
_MAX_WORKERS = 32


def _synthetic_def(index: int) -> _MarketDef:
    """A deterministic synthetic market def for catalog slot ``index`` (0-based).

    Derived PURELY from the index — no RNG ordering dependence, no shared state —
    so ``LUCKY_CAT_CATALOG=N`` always yields the identical extra catalog tail
    regardless of construction order or process. The seed price and daily vol are
    closed-form functions of the index so 500 coins span a realistic price/vol
    range without any per-symbol tuning. ``index`` is the slot AFTER the shipped
    defs (so the first synthetic symbol uses ``index == len(_MARKET_DEFS)``),
    keeping symbols collision-free with the shipped six.
    """
    base = f"SYN{index:03d}"
    symbol = f"{base}-MEOW"
    # Seed price cycles across magnitudes (sub-penny .. mid-cap) deterministically
    # so the synthetic catalog exercises every _price_dp / _size_unit band.
    tier = index % 5
    price0 = (0.02, 0.85, 12.5, 240.0, 5_200.0)[tier]
    # Daily vol walks a fixed band keyed on the index (0.02 .. ~0.099), stable.
    daily_vol = 0.02 + (index % 8) * 0.01
    return (symbol, base, "MEOW", f"Synth {index:03d}", price0, daily_vol)


def _resolve_market_defs() -> tuple[_MarketDef, ...]:
    """Resolve the catalog defs from ``LUCKY_CAT_CATALOG`` at SimFeed construction.

    Unset / invalid / ``N <= len(_MARKET_DEFS)`` returns the shipped defs verbatim
    (default stays exactly the 6 symbols). For ``N > len``, append ``N - len``
    deterministic synthetic defs. The shipped six are never reordered or
    perturbed, so the determinism golden holds at the default.
    """
    raw = os.environ.get(_CATALOG_ENV)
    if raw is None:
        return _MARKET_DEFS
    try:
        n = int(raw.strip())
    except ValueError:
        logger.warning(
            "%s=%r is not an int; using the default 6-market catalog.", _CATALOG_ENV, raw
        )
        return _MARKET_DEFS
    if n <= len(_MARKET_DEFS):
        return _MARKET_DEFS
    extra = tuple(_synthetic_def(i) for i in range(len(_MARKET_DEFS), n))
    return (*_MARKET_DEFS, *extra)


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
    # Per-level consumption overlay for the current step's synthetic ladder.
    # Cleared on each engine advance so user fills eat the live book snapshot.
    ask_consumed: dict[int, float]
    bid_consumed: dict[int, float]


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
        # Resolve the catalog ONCE at construction from LUCKY_CAT_CATALOG.
        # Default / N <= 6 == _MARKET_DEFS verbatim, so the determinism golden
        # stays green; N > 6 appends deterministic synthetic defs. Stored on the
        # instance so _init_states and the volatility lookup never re-read the env.
        self._defs: tuple[_MarketDef, ...] = _resolve_market_defs()
        # O(1) volatility lookup by symbol, built once from the resolved defs.
        # Replaces the old O(N) per-call linear scan over _MARKET_DEFS — at 500
        # coins the scan ran on every _advance_symbol (the hot path).
        self._vol_by_symbol: dict[str, float] = {d[0]: d[5] for d in self._defs}
        # Seconds between ``subscribe`` ticks (SSE cadence). This is presentation
        # pacing, *not* part of the deterministic engine — the tick *sequence* is
        # identical regardless of interval, so tests pass ``tick_interval=0`` to
        # exercise the engine at full speed.
        self._tick_interval = tick_interval
        self._lock = threading.Lock()
        # Worker pool for the per-tick fan-out. CPU-bound price work runs in
        # parallel under free-threading. Bounded to _MAX_WORKERS so a 500-coin
        # catalog does NOT spawn 500 OS threads — the fan-out width stays sane.
        # pool.map preserves result order regardless of worker count, so this does
        # NOT perturb the deterministic warmed snapshot (default 6 -> 6 workers).
        self._pool = ThreadPoolExecutor(
            max_workers=min(_MAX_WORKERS, max(2, len(self._defs))),
            thread_name_prefix="luckycat-tick",
        )
        self._states: dict[str, _SymbolState] = {}
        # Observability-only tick counter for the free-threading proof panel. Bumped once
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
        for symbol, base, quote, name, price0, _vol in self._defs:
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
                ask_consumed={},
                bid_consumed={},
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
        # O(1) lookup against the dict built at __init__ from the resolved defs.
        return self._vol_by_symbol.get(symbol, 0.03)

    def _advance_symbol(self, symbol: str) -> Tick:
        """Advance one symbol by a single step and return its update bundle.

        Honest CPU-bound work — no sleeps. Each symbol uses only its own PRNG
        and its own state slice, so this is safe to run concurrently across
        threads and the result is independent of fan-out order.
        """
        st = self._states[symbol]
        vol = self._vol_for(symbol)
        st.step += 1
        st.ask_consumed.clear()
        st.bid_consumed.clear()
        ts = float(st.step)

        # Free-threading proof: count this symbol-advance. Multiple worker
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

    def _raw_ladder_locked(self, st: _SymbolState) -> tuple[list[BookLevel], list[BookLevel]]:
        """Full synthetic bid/ask ladder for the current step (caller holds lock)."""
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
        return bids, asks

    @staticmethod
    def _apply_depth_consumed(
        levels: list[BookLevel], consumed: dict[int, float]
    ) -> tuple[BookLevel, ...]:
        """Subtract per-level consumption and drop depleted levels."""
        out: list[BookLevel] = []
        for i, lvl in enumerate(levels):
            rem = max(0.0, lvl.size - consumed.get(i, 0.0))
            if rem > 1e-9:
                out.append(BookLevel(price=lvl.price, size=round(rem, 6)))
        return tuple(out)

    def _book_locked(self, st: _SymbolState, depth: int) -> OrderBook:
        bids, asks = self._raw_ladder_locked(st)
        return OrderBook(
            symbol=st.market.symbol,
            bids=self._apply_depth_consumed(bids, st.bid_consumed)[:depth],
            asks=self._apply_depth_consumed(asks, st.ask_consumed)[:depth],
            ts=float(st.step),
        )

    def _consume_depth_locked(self, st: _SymbolState, side: str, size: float) -> None:
        """Eat size off the top of the bid or ask ladder. Caller holds ``self._lock``."""
        if size <= 0:
            return
        bids, asks = self._raw_ladder_locked(st)
        levels = asks if side == "buy" else bids
        consumed = st.ask_consumed if side == "buy" else st.bid_consumed
        remaining = size
        for i, lvl in enumerate(levels):
            avail = max(0.0, lvl.size - consumed.get(i, 0.0))
            if avail <= 1e-9:
                continue
            take = min(remaining, avail)
            consumed[i] = consumed.get(i, 0.0) + take
            remaining -= take
            if remaining <= 1e-9:
                break

    def _append_trade_locked(
        self, st: _SymbolState, side: str, size: float, price: float
    ) -> None:
        """Prepend a user fill to the tape. Caller holds ``self._lock``."""
        dp = self._price_dp(price)
        trade = Trade(
            id=st.next_trade_id,
            symbol=st.market.symbol,
            price=round(price, dp),
            size=round(size, 6),
            side=side,
            ts=float(st.step),
        )
        st.next_trade_id += 1
        st.trades.insert(0, trade)
        del st.trades[self._TAPE_MAX :]
        st.volume_24h += size

    # -- FeedSource protocol ----------------------------------------------

    def markets(self) -> tuple[Market, ...]:
        return tuple(st.market for st in self._states.values())

    # -- free-threading observability -------------------------------------

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

    def consume_depth(self, symbol: str, side: str, size: float) -> None:
        """Remove ``size`` from the top of the ask ladder (buy) or bid ladder (sell).

        Thread-safe mutation hook for the trade flow: a market buy eats the
        best asks; a market sell eats the best bids. Consumption is keyed to the
        current step's synthetic ladder and clears on the next engine advance.
        """
        if side not in ("buy", "sell"):
            raise ValueError(side)
        with self._lock:
            self._consume_depth_locked(self._require(symbol), side, size)

    def append_trade(self, symbol: str, side: str, size: float, price: float) -> None:
        """Append a user-executed print to the symbol's trade tape."""
        if side not in ("buy", "sell"):
            raise ValueError(side)
        with self._lock:
            self._append_trade_locked(self._require(symbol), side, size, price)

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
        # Live adapters are out of scope. Anything else is unknown
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
