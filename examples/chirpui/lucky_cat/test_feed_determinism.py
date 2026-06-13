"""DETERMINISM golden-snapshot regression test for the Lucky Cat SimFeed.

This is the *pinning* layer on top of the relational determinism tests in
``test_app.py`` (``TestSimFeed`` / ``TestIntervalCandles``). Those prove
*properties* (same seed => identical sequence, OHLC sanity, a == b). This file
freezes the *exact* warmed numbers so any regression to a nondeterministic
seeding scheme is caught the instant the literals drift.

Why these literals are process-stable (the things this test transitively guards):

* ``feed._sym_hash`` uses ``zlib.crc32`` (NOT builtin ``hash()``). Builtin
  ``hash(str)`` is salted per process via ``PYTHONHASHSEED``; ``crc32`` is stable
  everywhere. The sub-seed is ``(seed * 1_000_003) ^ (crc32(symbol) & 0xFFFF_FFFF)``
  and the book / interval / wick walks reseed off ``crc32`` too. The literals
  below were verified byte-identical across two processes and across
  ``PYTHONHASHSEED=0`` / ``=12345`` — any reversion to ``hash()`` flips them and
  fails this snapshot.
* ``_states`` / ``markets()`` are built from the ``_MARKET_DEFS`` tuple in a fixed
  order, so dict iteration never touches the numbers.
* Each symbol owns its own ``Random`` + state slice, so the ``ThreadPoolExecutor``
  fan-out in ``_advance_all`` is order-independent — one identical snapshot
  regardless of scheduling.
* Float formatting is pinned by the engine via ``round(..., _price_dp)`` (2dp
  >=1000, 4dp >=1, 6dp <1; pct 2dp; volume 4dp), so the literals are exact.

THE CALL SEQUENCE (process-restart-proof). Every test constructs its OWN
``SimFeed`` and calls ``reset()`` then ``warm()``:

    feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
    feed.reset()   # PURE restore to step-0 seed state — does NOT warm
    feed.warm()    # advances exactly _WARM_STEPS (24) — the get_feed() first-paint state

Instance ``SimFeed.reset()`` is a *pure restore* (step 0); it is the module-level
``feed.reset()`` (the one conftest calls) that does reset()+warm(). So a golden
test MUST construct its own instance and call both explicitly — it must never
touch ``get_feed()`` / ``feed._feed`` (shared mutable state mutated by other
tests). ``ts`` is the integer step counter (warmed = 24.0), so it is itself
deterministic and IS assertable — asserting ``ts == 24.0`` also locks the step
count, so a change to ``_WARM_STEPS`` is caught here.

These are plain sync methods: no ``example_app`` fixture, no async, no DB. The
autouse ``_lucky_cat_on_path`` fixture in ``conftest.py`` makes the in-body
``from feed import ...`` / ``from pages._context import ...`` work. Runs in <1s
(watchdog-safe).
"""


def _warmed_feed():
    """A freshly-constructed SimFeed at the canonical warmed snapshot.

    Pure-engine, no shared state — matches the existing ``TestSimFeed`` pattern
    of constructing ``SimFeed(seed=...)`` locally. Never use ``get_feed()``.
    """
    from feed import DEFAULT_SEED, SimFeed

    feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
    feed.reset()  # pure restore to step 0
    feed.warm()  # advance _WARM_STEPS (24) — the get_feed() first-paint state
    return feed


class TestSimFeedGoldenSnapshot:
    """Frozen warmed-state snapshot at ``seed=DEFAULT_SEED`` (0xCA7) after
    ``reset()`` + ``warm()`` (24 steps). If any of these literals drift, the
    determinism guarantee (crc32 seeding, fixed dict order, order-independent
    fan-out) has regressed."""

    def test_warmed_tickers_golden(self) -> None:
        """The full 6-symbol ticker dict, frozen.

        Tuple is (price, change_24h, change_pct_24h, high_24h, low_24h,
        volume_24h, ts). ``ts == 24.0`` for every symbol locks ``_WARM_STEPS``.
        """
        feed = _warmed_feed()
        golden = {
            "BTC-MEOW": (66941.08, 2941.08, 4.6, 66941.08, 62429.71, 1.2754, 24.0),
            "ETH-MEOW": (3752.05, 352.05, 10.35, 3752.05, 3152.53, 1.3228, 24.0),
            "SOL-MEOW": (128.1092, -16.8908, -11.65, 150.8133, 128.1092, 106.8079, 24.0),
            "DOGE-MEOW": (0.155037, -0.004963, -3.1, 0.16, 0.124841, 14917.9482, 24.0),
            "PAW-MEOW": (8.1024, -0.2976, -3.54, 8.7673, 6.6025, 176.1609, 24.0),
            "KOBAN-MEOW": (20.8698, -0.1302, -0.62, 21.3062, 19.4043, 139.5136, 24.0),
        }
        actual = {}
        for symbol in golden:
            t = feed.ticker(symbol)
            actual[symbol] = (
                t.price,
                t.change_24h,
                t.change_pct_24h,
                t.high_24h,
                t.low_24h,
                t.volume_24h,
                t.ts,
            )
        assert actual == golden

    def test_interval_candle_endpoints_golden(self) -> None:
        """1H / 1D / 1W synthetic-interval candle lengths + pinned endpoints.

        Endpoints are pinned by ``_interval_candles``: ``closes[0]`` == the 24h
        open (64000.0) and ``closes[-1]`` == the live price (66941.08), so the
        chart can never contradict the headline delta. The full first/last OHLC
        + ts of the 1H series are frozen too.
        """
        feed = _warmed_feed()

        # Synthetic-interval lengths (bucket counts) + pinned endpoint closes.
        for interval, length in (("1H", 60), ("1D", 48), ("1W", 52)):
            candles = feed.candles("BTC-MEOW", interval=interval, limit=64)
            assert len(candles) == length, interval
            assert candles[0].close == 64000.0, interval  # == 24h open (pinned)
            assert candles[-1].close == 66941.08, interval  # == live price (pinned)

        # Full first/last OHLCV + ts for the 1H series (the default chart tf).
        c1h = feed.candles("BTC-MEOW", interval="1H", limit=64)
        first, last = c1h[0], c1h[-1]
        assert (first.open, first.high, first.low, first.close, first.volume) == (
            64000.0,
            64375.55,
            63624.45,
            64000.0,
            0.510243,
        )
        assert (last.open, last.high, last.low, last.close, last.volume) == (
            66405.1,
            67007.38,
            66338.8,
            66941.08,
            0.487367,
        )
        assert first.ts == 0.0
        assert last.ts == 212400.0  # bucket index 59 * 3600s

    def test_1m_live_ring_golden(self) -> None:
        """The 1m live ring is a DISTINCT golden — it reads the live engine candle
        ring (aggregated from the per-tick walk), not the synthetic-interval walk.

        24 warm steps / ``_CANDLE_STEPS`` (12) == exactly 2 closed candles.
        """
        feed = _warmed_feed()
        ring = feed.candles("BTC-MEOW", interval="1m", limit=64)
        assert len(ring) == 2
        assert [c.close for c in ring] == [65154.3, 66941.08]

    def test_warmed_orderbook_golden(self) -> None:
        """Depth-3 synthetic order book: bids descending, asks ascending, frozen
        prices/sizes, ``ts == 24.0``. The ladder reseeds off ``crc32`` keyed on
        the step, so it is reproducible."""
        feed = _warmed_feed()
        book = feed.order_book("BTC-MEOW", depth=3)
        assert book.ts == 24.0
        assert [(b.price, b.size) for b in book.bids] == [
            (66914.31, 0.284022),
            (66887.53, 0.111965),
            (66860.75, 0.141562),
        ]
        assert [(a.price, a.size) for a in book.asks] == [
            (66967.86, 0.27638),
            (66994.64, 0.123082),
            (67021.41, 0.153583),
        ]

    def test_warmed_trades_golden(self) -> None:
        """Top-3 trade tape (newest first): frozen (id, price, size, side, ts)."""
        feed = _warmed_feed()
        trades = feed.trades("BTC-MEOW", limit=3)
        assert [(t.id, t.price, t.size, t.side, t.ts) for t in trades] == [
            (30, 66941.08, 0.020637, "sell", 24.0),
            (29, 66941.08, 0.03177, "buy", 24.0),
            (28, 65581.4, 0.005946, "sell", 23.0),
        ]

    def test_sparkline_and_hero_chart_golden(self) -> None:
        """The server-side sparkline + hero-chart geometry derived from the 1H
        closes. Direction (jade up) + endpoint crosshair samples are frozen so a
        seeding regression that flips the close series is caught at the geometry
        layer too."""
        from pages._context import _sparkline, hero_chart

        feed = _warmed_feed()
        closes = tuple(c.close for c in feed.candles("BTC-MEOW", interval="1H", limit=64))

        spark = _sparkline(closes)
        assert spark.ok is True
        assert spark.up is True
        assert spark.line.startswith("0.00,26.05 ")
        assert spark.area.startswith("0,36 ")
        assert spark.area.endswith(" 100,36")

        hero = hero_chart(closes, "1H")
        assert hero.ok is True
        assert len(hero.points) == 60
        assert hero.points[0] == (0.0, 26.05, 64000.0, "59h ago")
        assert hero.points[-1] == (100.0, 3.48, 66941.08, "now")
