"""Tests for the lucky_cat example.

#221 (scaffold): contract check is green, /health returns 200, and the landing
renders the Lucky Cat brand. #222 (this layer): the deterministic SimFeed powers
the markets grid + sidebar, and the same seed yields an identical tick sequence.
#223 appends market-detail + SSE coverage. #230/#231 cover the topbar deposit
flow and the progressive two-tier rail.

M2: #225 covers the trade flow (place/cancel + ValidationError 422 + multi-target
OOB + plain-POST FormAction redirect); #224 covers the portfolio Suspense
dashboard (shell + deferred blocks, with the `is deferred` empty-vs-loaded proof);
#227 Part A covers the visible free-threading proof panel and its live ticks/sec
SSE twin (honest parallel-work figures, no sleeps). app.check() stays clean
throughout (TestContracts).
"""

from chirp.testing import TestClient, assert_mutation_redirect
from tests.helpers.auth import extract_csrf_token, extract_session_cookie

_SESSION_COOKIE = "chirp_session_lucky_cat"


def _session_cookie(response) -> str | None:
    return extract_session_cookie(response, cookie_name=_SESSION_COOKIE)


class TestContracts:
    """The example should stay clean under startup contract checks."""

    def test_app_check_passes(self, example_app) -> None:
        example_app.check()


class TestHealth:
    """Railway healthcheck."""

    async def test_health_ok(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/health")
            assert response.status == 200
            assert response.text == "ok"


class TestLanding:
    """GET / renders the Lucky Cat shell + markets grid placeholder."""

    async def test_landing_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html" in response.text
            # Brand chrome + house token.
            assert "Lucky" in response.text
            assert "$MEOW" in response.text

    async def test_landing_has_markets_grid(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'id="markets-grid"' in response.text
            assert 'id="lucky-cat-ticker"' in response.text

    async def test_landing_renders_live_markets(self, example_app) -> None:
        """#222: the SimFeed populates the grid and sidebar (no empty state)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            # SimFeed ships these markets; both grid card + sidebar link render.
            assert "BTC-MEOW" in response.text
            assert "ETH-MEOW" in response.text
            # Live (simulated) price + 24h change chrome.
            assert "luckycat-market-card__price" in response.text
            assert "luckycat-market-card__change" in response.text
            # The #221 empty state must be gone now that markets are live.
            assert "No markets open yet" not in response.text

    async def test_landing_renders_no_raw_template_tags(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "{%" not in response.text
            assert "{{" not in response.text

    async def test_landing_has_no_duplicate_element_ids(self, example_app) -> None:
        """No static element id may appear twice in the full-page render. A
        duplicate id is invalid HTML and silently breaks getElementById /
        aria-controls / Alpine $id wiring. This guards a real regression: the
        mobile drawer once rendered chirp-ui's ``shell_actions_bar`` (which bakes
        a FIXED ``#{target}-overflow`` id) while the topbar rendered it too, so
        the id existed twice. The drawer now renders its actions as plain rows
        (``drawer_actions``) precisely to keep every id unique."""
        import re

        async with TestClient(example_app) as client:
            response = await client.get("/")
        # Static ids only (``id="..."`` preceded by whitespace, so ``grid="`` and
        # Alpine ``:id``/``x-id`` dynamic bindings are not matched).
        ids = re.findall(r'\sid="([^"]+)"', response.text)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        assert not dupes, f"duplicate element ids in GET /: {dupes}"

    async def test_landing_cards_render_gradient_sparkline(self, example_app) -> None:
        """Each warmed market card carries a server-rendered gradient-area SVG
        sparkline — no JS chart lib, drawn from the candle-close series."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            assert response.status == 200
            # One SVG sparkline + its gradient fill polygon + line polyline per card.
            assert "luckycat-spark " in html
            assert "luckycat-spark__line" in html
            assert "luckycat-spark__fill" in html
            # Direction is keyed off the series (up=jade / down=red) and the
            # gradient id is namespaced by symbol so multiple cards never collide.
            assert "luckycat-spark--up" in html or "luckycat-spark--down" in html
            assert 'id="lc-spark-BTC-MEOW-' in html

    async def test_landing_cards_mark_direction(self, example_app) -> None:
        """Cards carry an up/down modifier so the top-edge accent + delta pill
        agree on direction."""
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
            assert "luckycat-market-card--up" in html or "luckycat-market-card--down" in html

    async def test_landing_sparkline_survives_boosted_nav(self, example_app) -> None:
        """The sparkline lives inside page_content, so a boosted (htmx) re-render
        of the markets grid keeps the charts — not just the first full-page paint."""
        async with TestClient(example_app) as client:
            response = await client.get("/", headers={"HX-Request": "true", "HX-Boosted": "true"})
            assert response.status == 200
            assert "luckycat-spark " in response.text


class TestSparklineGeometry:
    """Unit coverage for the server-side sparkline geometry helper (no JS chart)."""

    def test_too_few_points_is_not_ok(self) -> None:
        from pages._context import _sparkline

        assert _sparkline(()).ok is False
        assert _sparkline((1.0,)).ok is False

    def test_direction_keyed_off_first_vs_last(self) -> None:
        from pages._context import _sparkline

        assert _sparkline((1.0, 2.0, 3.0)).up is True
        assert _sparkline((3.0, 2.0, 1.0)).up is False

    def test_points_span_full_viewbox_width(self) -> None:
        from pages._context import _sparkline

        spark = _sparkline((10.0, 20.0, 15.0, 30.0))
        coords = [p.split(",") for p in spark.line.split(" ")]
        xs = [float(x) for x, _ in coords]
        ys = [float(y) for _, y in coords]
        # x spans 0..100; y stays inside the 0..36 grid (with 2px breathing room).
        assert xs[0] == 0.0
        assert xs[-1] == 100.0
        assert all(2.0 <= y <= 34.0 for y in ys)
        # The fill polygon closes the line down to the baseline (y=36).
        assert spark.area.startswith("0,36 ")
        assert spark.area.endswith(" 100,36")

    def test_flat_series_pins_to_midline(self) -> None:
        from pages._context import _sparkline

        spark = _sparkline((5.0, 5.0, 5.0))
        ys = {p.split(",")[1] for p in spark.line.split(" ")}
        assert ys == {"18.00"}


class TestSimFeed:
    """#222: the FeedSource seam + the deterministic SimFeed."""

    def test_implements_feedsource_protocol(self) -> None:
        from feed import FeedSource, SimFeed

        assert isinstance(SimFeed(seed=1), FeedSource)

    def test_markets_populated(self) -> None:
        from feed import Market, SimFeed

        feed = SimFeed(seed=1)
        markets = feed.markets()
        assert len(markets) >= 4
        assert all(isinstance(m, Market) for m in markets)
        # Everything is priced in the house token $MEOW.
        assert all(m.quote == "MEOW" for m in markets)

    def test_default_feed_is_sim(self, monkeypatch) -> None:
        import feed as feed_mod

        monkeypatch.delenv("LUCKY_CAT_FEED", raising=False)
        feed_mod._feed = None
        try:
            source = feed_mod.get_feed()
            assert isinstance(source, feed_mod.SimFeed)
        finally:
            feed_mod._feed = None

    def test_unknown_feed_falls_back_to_sim(self, monkeypatch, caplog) -> None:
        import logging

        import feed as feed_mod

        monkeypatch.setenv("LUCKY_CAT_FEED", "kraken")
        feed_mod._feed = None
        try:
            with caplog.at_level(logging.WARNING, logger="lucky_cat.feed"):
                source = feed_mod.get_feed()
            assert isinstance(source, feed_mod.SimFeed)
            assert any("falling back" in r.message for r in caplog.records)
        finally:
            feed_mod._feed = None

    def test_snapshots_render(self) -> None:
        """ticker / order_book / trades / candles all populate after ticks."""
        import asyncio

        from feed import BookLevel, Candle, OrderBook, Ticker, Trade

        async def drive() -> None:
            from feed import SimFeed

            feed = SimFeed(seed=7, tick_interval=0)
            symbol = feed.markets()[0].symbol
            agen = feed.subscribe(symbol)
            # Drive enough steps to fill the tape and at least one candle.
            for _ in range(15):
                await agen.__anext__()
            await agen.aclose()

            ticker = feed.ticker(symbol)
            assert isinstance(ticker, Ticker)
            assert ticker.price > 0

            book = feed.order_book(symbol, depth=8)
            assert isinstance(book, OrderBook)
            assert len(book.bids) == 8
            assert len(book.asks) == 8
            assert all(isinstance(b, BookLevel) for b in book.bids)
            # bids descending, asks ascending, bid < ask.
            assert book.bids[0].price > book.bids[-1].price
            assert book.asks[0].price < book.asks[-1].price
            assert book.bids[0].price < book.asks[0].price

            trades = feed.trades(symbol, limit=10)
            assert len(trades) > 0
            assert all(isinstance(t, Trade) for t in trades)
            assert all(t.side in ("buy", "sell") for t in trades)

            candles = feed.candles(symbol)
            assert len(candles) >= 1
            assert all(isinstance(c, Candle) for c in candles)

        asyncio.run(drive())

    def test_same_seed_identical_tick_sequence(self) -> None:
        """The headline determinism guarantee: seed -> identical ticks."""
        import asyncio

        from feed import SimFeed

        async def run_one(seed: int) -> list:
            feed = SimFeed(seed=seed, tick_interval=0)
            symbol = feed.markets()[0].symbol
            agen = feed.subscribe(symbol)
            seq = []
            for _ in range(20):
                tick = await agen.__anext__()
                seq.append((tick.ticker.price, tick.ticker.volume_24h, len(tick.trades)))
            await agen.aclose()
            return seq

        a = asyncio.run(run_one(0xCA7))
        b = asyncio.run(run_one(0xCA7))
        c = asyncio.run(run_one(0x1234))
        assert a == b
        # Different seed should diverge (sanity: not a constant sequence).
        assert a != c

    def test_reset_restores_seed_state(self) -> None:
        import asyncio

        from feed import SimFeed

        async def drive(feed: SimFeed) -> float:
            symbol = feed.markets()[0].symbol
            agen = feed.subscribe(symbol)
            price = 0.0
            for _ in range(10):
                tick = await agen.__anext__()
                price = tick.ticker.price
            await agen.aclose()
            return price

        feed = SimFeed(seed=0xCA7, tick_interval=0)
        first = asyncio.run(drive(feed))
        feed.reset()
        second = asyncio.run(drive(feed))
        assert first == second


class TestIntervalCandles:
    """Chart interactivity (#chart): per-interval candles are deterministic,
    correctly bucketed, OHLC-sane, and agree with the 24h delta direction."""

    def test_intervals_contract(self) -> None:
        from feed import DEFAULT_INTERVAL, INTERVALS

        # 1m (live ring) first, then the synthetic coarse timeframes.
        assert INTERVALS[0] == "1m"
        assert set(INTERVALS) == {"1m", "1H", "1D", "1W"}
        assert DEFAULT_INTERVAL in INTERVALS

    def test_interval_candles_are_deterministic(self) -> None:
        """Same seed => identical per-interval candle series (the headline
        determinism guarantee, extended to the chart timeframes)."""
        from feed import SimFeed

        a = SimFeed(seed=0xCA7, tick_interval=0)
        a.warm()
        b = SimFeed(seed=0xCA7, tick_interval=0)
        b.warm()
        symbol = a.markets()[0].symbol
        for interval in ("1H", "1D", "1W"):
            assert a.candles(symbol, interval=interval, limit=64) == b.candles(
                symbol, interval=interval, limit=64
            )

    def test_interval_candles_are_bucketed(self) -> None:
        """Each coarse interval buckets ts at its own period, oldest→newest, with
        a deterministic bucket count and a sane OHLC envelope."""
        from feed import _INTERVAL_DEFS, Candle, SimFeed

        feed = SimFeed(seed=7, tick_interval=0)
        feed.warm()
        symbol = feed.markets()[0].symbol
        for interval, (seconds, count, _vol) in _INTERVAL_DEFS.items():
            candles = feed.candles(symbol, interval=interval, limit=count)
            assert len(candles) == count
            assert all(isinstance(c, Candle) for c in candles)
            # ts is the bucket index * the interval period (oldest=0), strictly
            # increasing by exactly one period per bucket.
            assert [c.ts for c in candles] == [i * seconds for i in range(count)]
            # OHLC envelope: low <= open/close <= high, prices positive.
            assert all(
                c.low <= c.open <= c.high and c.low <= c.close <= c.high and c.low > 0
                for c in candles
            )

    def test_interval_limit_caps_count(self) -> None:
        from feed import SimFeed

        feed = SimFeed(seed=7, tick_interval=0)
        feed.warm()
        symbol = feed.markets()[0].symbol
        assert len(feed.candles(symbol, interval="1D", limit=10)) == 10

    def test_interval_series_ends_at_live_price(self) -> None:
        """The series' last close pins to the current live price so the focal
        chart matches the live ticker numeral."""
        from feed import SimFeed

        feed = SimFeed(seed=0xCA7, tick_interval=0)
        feed.warm()
        symbol = feed.markets()[0].symbol
        price = feed.ticker(symbol).price
        for interval in ("1H", "1D", "1W"):
            last = feed.candles(symbol, interval=interval, limit=64)[-1].close
            assert abs(last - price) <= max(0.01, price * 0.001)

    def test_chart_direction_agrees_with_24h_delta(self) -> None:
        """Endpoints are pinned (first=24h open, last=live), so the chart's
        first-vs-last direction always matches the 24h delta pill — jade up /
        red down can never contradict the headline number."""
        from feed import SimFeed
        from pages._context import hero_chart

        feed = SimFeed(seed=0xCA7, tick_interval=0)
        feed.warm()
        for market in feed.markets():
            delta_up = feed.ticker(market.symbol).change_pct_24h >= 0
            for interval in ("1H", "1D", "1W"):
                closes = tuple(
                    c.close for c in feed.candles(market.symbol, interval=interval, limit=64)
                )
                assert hero_chart(closes, interval).up is delta_up

    def test_unknown_interval_falls_back_to_live_ring(self) -> None:
        from feed import SimFeed

        feed = SimFeed(seed=7, tick_interval=0)
        feed.warm()
        symbol = feed.markets()[0].symbol
        assert feed.candles(symbol, interval="nonsense", limit=64) == feed.candles(
            symbol, interval="1m", limit=64
        )

    def test_hero_chart_geometry_carries_crosshair_points(self) -> None:
        """The HeroChart geometry exposes JSON-safe per-point crosshair samples
        (x, y, price, label) for the nonced data island."""
        from pages._context import hero_chart

        hc = hero_chart((10.0, 20.0, 15.0, 30.0), "1H")
        assert hc.ok is True
        assert len(hc.points) == 4
        x0, y0, price0, _label0 = hc.points[0]
        assert x0 == 0.0
        assert 0.0 <= y0 <= 36.0
        assert price0 == 10.0
        assert hc.points[-1][3] == "now"  # newest bucket label
        # Geometry contract matches the sparkline (same viewBox + area baseline).
        assert hc.area.startswith("0,36 ")
        assert hc.area.endswith(" 100,36")


class TestMarketDetail:
    """#223: GET /markets/{symbol} renders the live trading view as a full page."""

    async def test_detail_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/BTC-MEOW")
            assert response.status == 200
            assert "<html" in response.text
            assert "BTC-MEOW" in response.text
            # Shell chrome still present (composition into the app shell).
            assert "$MEOW" in response.text
            assert 'id="lucky-cat-ticker"' in response.text

    async def test_detail_has_live_regions(self, example_app) -> None:
        """All three live regions render with their canonical DOM ids."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/ETH-MEOW")
            assert response.status == 200
            assert 'id="market-ticker"' in response.text
            assert 'id="order-book"' in response.text
            assert 'id="trade-tape"' in response.text
            # Order-book bid/ask rows + trade-tape rows render from the snapshot.
            assert "luckycat-orderbook__row--bid" in response.text
            assert "luckycat-orderbook__row--ask" in response.text
            assert "luckycat-tape__row" in response.text

    async def test_detail_has_info_anchor_section(self, example_app) -> None:
        """IA: the inner-rail "this market" lane ships an Info anchor (#info), so
        the detail page must have a REAL id="info" section (not a dead-end jump).
        The static meta panel renders the market's pair from the Market def."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/ETH-MEOW")
            assert response.status == 200
            html = response.text
            # The real scroll target for the rail's #info anchor.
            assert 'id="info"' in html
            assert "luckycat-detail__info" in html
            # The static meta renders the pair (base/quote) — never raw tags.
            assert "ETH/MEOW" in html
            assert "{%" not in html
            assert "{{" not in html

    async def test_detail_wires_sse_scope(self, example_app) -> None:
        """The detail page opens the per-market SSE channel."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/SOL-MEOW")
            assert response.status == 200
            assert 'sse-connect="/markets/SOL-MEOW/stream"' in response.text
            assert 'hx-ext="sse"' in response.text

    async def test_detail_full_page_has_no_oob_attribute(self, example_app) -> None:
        """The browser-navigation render must NOT carry an hx-swap-oob *attribute*
        — that is reserved for the SSE fragment twins (otherwise htmx would
        mis-route the initial paint). The attribute form ``hx-swap-oob="``
        excludes the chirpui SSE-helper script's ``"hx-swap-oob"`` string
        literal, which is not a real OOB element."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/BTC-MEOW")
            assert response.status == 200
            assert 'hx-swap-oob="' not in response.text

    async def test_detail_unknown_symbol_404(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/NOPE-MEOW")
            assert response.status == 404

    async def test_detail_renders_no_raw_template_tags(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/BTC-MEOW")
            assert "{%" not in response.text
            assert "{{" not in response.text


class TestMarketStream:
    """#223: GET /markets/{symbol}/stream pushes OOB fragments as ticks arrive."""

    async def test_stream_is_event_stream(self, example_app) -> None:
        async with TestClient(example_app) as client:
            result = await client.sse("/markets/BTC-MEOW/stream", max_events=4)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) >= 4

    async def test_stream_events_are_oob_fragments(self, example_app) -> None:
        """Every HTML event is an OOB swap with no raw template tags."""
        async with TestClient(example_app) as client:
            result = await client.sse("/markets/ETH-MEOW/stream", max_events=8)
        html_events = [e for e in result.events if e.data]
        assert len(html_events) >= 4
        for evt in html_events:
            # Fragment SSE events ride the default message channel.
            assert (evt.event or "message") == "message", (
                f"Expected message channel, got {evt.event!r}"
            )
            assert "{{" not in evt.data
            assert "{%" not in evt.data
        oob_events = [e for e in html_events if "hx-swap-oob" in e.data]
        assert len(oob_events) >= 4

    async def test_stream_targets_match_full_page_ids(self, example_app) -> None:
        """The OOB swap targets must match the DOM ids in the full-page render
        (the fail-loud SSE OOB invariant)."""
        async with TestClient(example_app) as client:
            result = await client.sse("/markets/SOL-MEOW/stream", max_events=12)
        joined = "".join(e.data for e in result.events if e.data)
        assert 'id="market-ticker"' in joined
        assert 'id="order-book"' in joined
        assert 'id="trade-tape"' in joined
        # The cross-page topbar strip (#lucky-cat-ticker) is NOT driven by the
        # per-market stream — it is owned by the global `ticker` SIGNAL (over the
        # one /_chirp/live connection) so a single source updates it on every page
        # (no two-source flicker). See TestTickerStream for the strip's coverage.
        assert 'id="lucky-cat-ticker"' not in joined

    async def test_stream_reflects_requested_market(self, example_app) -> None:
        """The per-market stream is bound to its route's symbol. (The symbol
        STRING used to ride the cross-page strip twin; that moved to the global
        `ticker` SIGNAL on /_chirp/live, so specificity is now checked via the
        live data itself: two different markets yield different deterministic hero
        prices — DOGE (~0.14) is far cheaper than BTC (~66000).)"""
        import re

        async with TestClient(example_app) as client:
            doge = await client.sse("/markets/DOGE-MEOW/stream", max_events=4)
            btc = await client.sse("/markets/BTC-MEOW/stream", max_events=4)

        def first_price(result):
            joined = "".join(e.data for e in result.events if e.data)
            match = re.search(r'luckycat-hero-ticker__price">([\d.]+)<', joined)
            return float(match.group(1)) if match else None

        dp, bp = first_price(doge), first_price(btc)
        assert dp is not None
        assert bp is not None
        assert dp != bp  # distinct markets → distinct deterministic prices
        assert dp < bp  # DOGE-MEOW is sub-dollar; BTC-MEOW is in the tens of thousands


class TestTickerStream:
    """The topbar ticker strip (#lucky-cat-ticker) is global chrome, live on
    EVERY page via the `ticker` SIGNAL (a rotating market spotlight) over the one
    shared /_chirp/live connection. signal_block('ticker') paints an
    `sse-swap="ticker"` sink inside the #lucky-cat-ticker wrapper, SSR-seeded so
    it never sits on "Waiting…"; every `event: ticker` over /_chirp/live
    innerHTML-swaps it. It is the SOLE owner of the strip (the per-market detail
    stream does not also swap it — see
    TestMarketStream.test_stream_targets_match_full_page_ids)."""

    async def test_shell_opens_signal_connection(self, example_app) -> None:
        """The persistent shell opens the one shared /_chirp/live connection on
        every page (signal_connect()), and the topbar strip carries the ticker
        signal sink under it (sse-swap="ticker"). The connect is the SINGLE
        persistent connection on the page (the headline N→1 fold)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
        assert response.status == 200
        # The single merged signal connection (replacing the old /ticker/stream +
        # /notifications/stream sse_scopes) — exactly ONE sse-connect per page. It
        # carries an absent/empty ?topics, which the stream resolves to subscribe-
        # all (signal_connect() renders at the top of the shell, before the topbar
        # sinks record their topics — so the bare connect streams every signal).
        assert 'sse-connect="/_chirp/live' in response.text
        assert response.text.count("sse-connect=") == 1
        # The ticker signal sink lives inside the #lucky-cat-ticker wrapper.
        assert 'id="lucky-cat-ticker"' in response.text
        strip = response.text[response.text.find('id="lucky-cat-ticker"') :]
        assert 'sse-swap="ticker"' in strip

    async def test_ticker_signal_binding_is_ssr_seeded(self, example_app) -> None:
        """GET / paints the signal_block('ticker') sink already seeded with a real
        market spotlight (the ▲/▼ strip), so there is no empty-then-fill flash."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
        assert response.status == 200
        strip = response.text[response.text.find('id="lucky-cat-ticker"') :]
        # SSR seed: a real market + the directional arrow (a11y: not color alone).
        assert "-MEOW" in strip
        assert "luckycat-ticker__arrow" in strip
        assert "▲" in strip or "▼" in strip
        assert "{{" not in response.text
        assert "{%" not in response.text

    async def test_ticker_signal_stream_is_event_stream(self, example_app) -> None:
        """The merged /_chirp/live stream is an EventStream that emits the ticker
        topic when scoped to ?topics=ticker."""
        async with TestClient(example_app) as client:
            result = await client.sse("/_chirp/live?topics=ticker", max_events=2)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        assert len(result.events) >= 1

    async def test_ticker_signal_emits_strip_with_arrow(self, example_app) -> None:
        """The merged stream emits `event: ticker` carrying the SAME strip body the
        layout paints — a real market spotlight, the directional ▲/▼ glyph (a11y:
        not color alone), and no leaked raw template tags. The signal sink owns the
        sse-swap binding, so the payload itself bakes no id / hx-swap-oob twin."""
        async with TestClient(example_app) as client:
            result = await client.sse("/_chirp/live?topics=ticker", max_events=2)
        ticker_events = [e for e in result.events if e.event == "ticker" and e.data]
        assert ticker_events, f"no event: ticker frames: {[e.event for e in result.events]}"
        joined = "".join(e.data for e in ticker_events)
        assert "-MEOW" in joined  # a real market spotlight, not the "Waiting…" hint
        assert "luckycat-ticker__arrow" in joined
        assert "▲" in joined or "▼" in joined
        assert "{{" not in joined
        assert "{%" not in joined


class TestMarketChart:
    """Chart interactivity (#chart): GET /markets/{symbol}/chart?tf= returns the
    hero-chart fragment for each timeframe, with the toggle wired to OVERRIDE the
    inherited boosted-shell outlet (the convert-form footgun pattern)."""

    async def test_chart_fragment_per_timeframe(self, example_app) -> None:
        """Every timeframe returns a 200 fragment carrying the #market-chart
        region, with no leaked raw template tags and the active tf pressed."""
        from feed import INTERVALS

        async with TestClient(example_app) as client:
            for tf in INTERVALS:
                response = await client.get(
                    f"/markets/BTC-MEOW/chart?tf={tf}",
                    headers={"HX-Request": "true"},
                )
                assert response.status == 200, tf
                body = response.text
                assert 'id="market-chart"' in body, tf
                assert "luckycat-chart-toggle" in body, tf
                # The requested timeframe button is the pressed/active one.
                assert 'aria-pressed="true"' in body, tf
                assert f">{tf}</button>" in body, tf
                # Fragment is fully rendered — no leaked template syntax.
                assert "{{" not in body, tf
                assert "{%" not in body, tf

    async def test_chart_toggle_overrides_inherited_outlet(self, example_app) -> None:
        """The toggle buttons must override the inherited #main / #page-content
        target+select with their OWN #market-chart region, or the swap lands
        empty inside the boosted shell."""
        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/BTC-MEOW/chart?tf=1H", headers={"HX-Request": "true"}
            )
        body = response.text
        assert 'hx-target="#market-chart"' in body
        assert 'hx-select="#market-chart"' in body
        assert 'hx-swap="outerHTML"' in body
        # The toggle hx-gets the chart route per timeframe.
        assert 'hx-get="/markets/BTC-MEOW/chart?tf=1D"' in body

    async def test_chart_fragment_carries_crosshair_island(self, example_app) -> None:
        """The fragment ships a nonced JSON data island + the crosshair hooks the
        vanilla controller reads (no eval, no Alpine dependency)."""
        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/ETH-MEOW/chart?tf=1D", headers={"HX-Request": "true"}
            )
        body = response.text
        assert 'id="lc-chart-data-ETH-MEOW"' in body
        assert 'type="application/json"' in body
        assert "data-luckycat-chart" in body
        assert "data-luckycat-crosshair" in body

    async def test_chart_unknown_timeframe_clamps_to_default(self, example_app) -> None:
        """A tampered/unknown tf clamps to the default timeframe rather than
        reaching the feed as an arbitrary interval."""
        from feed import DEFAULT_INTERVAL

        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/BTC-MEOW/chart?tf=%2Fevil", headers={"HX-Request": "true"}
            )
        assert response.status == 200
        assert f">{DEFAULT_INTERVAL}</button>" in response.text
        assert 'aria-pressed="true"' in response.text

    async def test_chart_unknown_symbol_404(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/NOPE-MEOW/chart?tf=1H", headers={"HX-Request": "true"}
            )
        assert response.status == 404

    async def test_detail_full_page_renders_chart_toggle(self, example_app) -> None:
        """The full-page market detail paints the chart region + the timeframe
        toggle (the toggle is part of the initial paint, not JS-injected)."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/SOL-MEOW")
        body = response.text
        assert 'id="market-chart"' in body
        assert "luckycat-chart-toggle" in body
        assert 'id="lc-chart-data-SOL-MEOW"' in body


class TestTopbar:
    """#230: the topbar chrome is real — Deposit opens a modal that POSTs, and
    the bar uses more than one shell-action zone."""

    async def test_deposit_action_is_not_inert(self, example_app) -> None:
        """The Deposit button carries data-action="deposit" (the kanban modal
        pattern), NOT an inert href="#"."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'data-action="deposit"' in response.text
            # The old inert placeholder must be gone.
            assert 'href="#"' not in response.text

    async def test_topbar_holds_only_global_actions(self, example_app) -> None:
        """IA doctrine: the topbar holds global actions only — Deposit (primary)
        + About (overflow). Section navigation (Markets) lives in the outer icon
        rail, NOT the topbar, so there is no 'controls' nav zone."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "chirpui-shell-actions__group--primary" in response.text
            # Overflow auto-wraps into a "More" dropdown.
            assert "chirpui-shell-actions__group--overflow" in response.text
            assert "More" in response.text
            # No 'controls' zone: section nav does not belong in the topbar.
            assert "chirpui-shell-actions__group--controls" not in response.text

    async def test_deposit_modal_present(self, example_app) -> None:
        """The deposit dialog + its CSRF-protected form ship inside the page."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'id="deposit-modal"' in response.text
            assert 'id="deposit-form"' in response.text
            # The form is CSRF-protected (hidden field) and posts to /deposit.
            assert 'name="_csrf_token"' in response.text
            assert 'hx-post="/deposit"' in response.text

    async def test_balance_renders_in_topbar(self, example_app) -> None:
        """The $MEOW balance is a live `balance` SIGNAL: the topbar token carries
        an sse-swap="balance" sink (signal('balance')) SSR-seeded with the seed
        value. No #lucky-cat-balance OOB id anymore — the signal sink owns it."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            # The balance signal binding (the helper emits
            # <span sse-swap="balance" hx-target="this">…</span>).
            assert 'sse-swap="balance"' in response.text
            # ...inside the topbar token chrome.
            token = response.text[response.text.find("luckycat-token__amount") :]
            assert 'sse-swap="balance"' in token
            # SSR seed balance from wallet.INITIAL_MEOW.
            assert "1000" in response.text
            assert "$MEOW" in response.text

    async def test_deposit_emits_balance_signal(self, example_app) -> None:
        """POST /deposit credits the wallet and EMITS the `balance` signal — the
        visible update fans over /_chirp/live to every signal('balance') binding,
        so the response itself is an empty 204 (the form posts hx-swap="none").
        No hand-maintained OOB twin (the migration's whole point)."""
        import wallet

        wallet.reset()
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _session_cookie(page)
            csrf = extract_csrf_token(page.text)
            assert csrf is not None
            headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}
            if cookie:
                headers["Cookie"] = f"{_SESSION_COOKIE}={cookie}"
            before = wallet.balance()
            response = await client.post("/deposit", data={"amount": "250"}, headers=headers)
            # Empty 204: the live signal carries the visible update, not the body.
            assert response.status == 204
            assert response.text == ""
            # The wallet was credited (the value the signal emits to every binding).
            assert wallet.balance() == before + 250

    async def test_deposit_clamps_bad_amount(self, example_app) -> None:
        """A non-numeric/negative amount is a no-op credit — balance never drops.
        The route still returns its empty 204 (the signal emits the unchanged
        value); the clamp is asserted on the wallet, not a rendered body."""
        import wallet

        wallet.reset()
        async with TestClient(example_app) as client:
            page = await client.get("/")
            cookie = _session_cookie(page)
            csrf = extract_csrf_token(page.text)
            headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}
            if cookie:
                headers["Cookie"] = f"{_SESSION_COOKIE}={cookie}"
            before = wallet.balance()
            response = await client.post(
                "/deposit", data={"amount": "not-a-number"}, headers=headers
            )
            assert response.status == 204
            # Balance unchanged at the seed value (a clamped no-op credit).
            assert wallet.balance() == before

    async def test_deposit_requires_csrf(self, example_app) -> None:
        """Without a CSRF token the mutating route is rejected (secure-by-default)."""
        async with TestClient(example_app) as client:
            response = await client.post("/deposit", data={"amount": "100"})
            assert response.status in (400, 403)


class TestCommandPalette:
    """The Cmd/Ctrl-K command palette: the dialog ships in the persistent shell
    and the /search route filters the markets + rooms directory server-side,
    returning the same palette_results_body block the shell renders at rest."""

    async def test_palette_dialog_renders_in_shell(self, example_app) -> None:
        """The <dialog> + ⌘K trigger + the resting (unfiltered) directory ship on
        every page (the layout renders the palette as a persistent shell region)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            # The native <dialog> the chirpuiDialogTarget controller opens on ⌘K.
            assert 'id="command-palette"' in response.text
            # The results container the /search route swaps into.
            assert 'id="command-palette-results"' in response.text
            # The ⌘K trigger affordance in the topbar.
            assert "⌘K" in response.text
            # The resting palette shows the full directory: markets + the rooms.
            assert "BTC-MEOW" in response.text
            assert "ETH-MEOW" in response.text
            # The "Go to" rooms group is present.
            assert "Go to" in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_search_filters_to_eth_and_a_room(self, example_app) -> None:
        """GET /search?q=eth returns the palette_results_body fragment (no shell)
        filtered to the ETH market and the Settings room (whose label contains
        'set'… no — 'eth' matches no room). 'eth' matches the ETH-MEOW market;
        we also assert a room query narrows correctly below."""
        async with TestClient(example_app) as client:
            response = await client.get("/search", query={"q": "eth"})
            assert response.status == 200
            # A fragment, not a full page (no shell <html>).
            assert "<html" not in response.text
            # ETH market matched.
            assert "ETH-MEOW" in response.text
            # Other markets filtered OUT (BTC does not contain 'eth').
            assert "BTC-MEOW" not in response.text
            assert "DOGE-MEOW" not in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_search_matches_a_room(self, example_app) -> None:
        """A query that hits a room key/label narrows the 'Go to' group to it —
        proving both directories (markets + rooms) are searched."""
        async with TestClient(example_app) as client:
            response = await client.get("/search", query={"q": "portfolio"})
            assert response.status == 200
            # The Portfolio room link is present...
            assert "/portfolio" in response.text
            assert "Portfolio" in response.text
            # ...and markets (no 'portfolio' substring) are filtered out.
            assert "BTC-MEOW" not in response.text

    async def test_empty_query_returns_full_directory(self, example_app) -> None:
        """An empty q returns the whole directory (the resting palette state):
        every market + every room, all crawlable in-app hrefs."""
        async with TestClient(example_app) as client:
            response = await client.get("/search", query={"q": ""})
            assert response.status == 200
            for symbol in ("BTC-MEOW", "ETH-MEOW", "SOL-MEOW", "DOGE-MEOW"):
                assert symbol in response.text, symbol
            # All five rooms present.
            for label in ("Markets", "Portfolio", "Trade", "Activity", "Settings"):
                assert label in response.text, label
            # Real result links carry the boosted shell-outlet contract.
            assert 'href="/markets/ETH-MEOW"' in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_palette_input_has_combobox_semantics(self, example_app) -> None:
        """A11y: the search-as-you-type palette exposes combobox/listbox roles so
        AT knows typing filters a list (the rich Enter-selects-first behavior was
        otherwise invisible). The results region is a polite listbox so result
        changes are announced; each result item is role="option"."""
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
            assert 'role="combobox"' in html
            assert 'aria-controls="command-palette-results"' in html
            assert 'aria-autocomplete="list"' in html
            # The results region is a polite listbox.
            results = html[html.find('id="command-palette-results"') :]
            assert 'role="listbox"' in results
            assert 'aria-live="polite"' in results
            # Result items are options.
            assert 'role="option"' in html

    async def test_palette_can_reach_watchlist(self, example_app) -> None:
        """IA: the ⌘K palette is the "go anywhere" surface, so it must reach the
        Watchlist (the one functional non-room destination) — not only the rail.
        A 'watchlist' query narrows the Go-to group to it."""
        async with TestClient(example_app) as client:
            response = await client.get("/search", query={"q": "watchlist"})
            assert response.status == 200
            assert 'href="/watchlist"' in response.text
            assert "Starred markets" in response.text
            # Markets (no 'watchlist' substring) are filtered out.
            assert "BTC-MEOW" not in response.text


class TestActivityFeed:
    """The Activity landing is a real MERGED feed (deposits + fills interleaved
    by ts, newest first), not the old static 'No activity yet' stub."""

    async def test_landing_is_merged_feed_not_static_stub(self, example_app) -> None:
        """With a deposit and a fill on record, the landing renders BOTH rows in
        the shared fills table — never the old stub copy that asserted no data."""
        import trade_store
        import wallet

        wallet.deposit(250)
        trade_store.place_order("PAW-MEOW", "buy", "market", 1.0)
        async with TestClient(example_app) as client:
            response = await client.get("/activity")
            assert response.status == 200
            assert "<html" in response.text
            # The fill row (a traded market) + the deposit row both render.
            assert "PAW-MEOW" in response.text
            assert "DEPOSIT" in response.text
            assert "+250 $MEOW" in response.text
            # The old static stub copy is gone.
            assert "No activity yet — make a deposit to get started." not in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_landing_empty_shows_maneki_empty_state(self, example_app) -> None:
        """With both sources empty (seed state), the polished maneki empty state
        shows — and the copy never asserts data it does not render."""
        async with TestClient(example_app) as client:
            response = await client.get("/activity")
            assert response.status == 200
            assert "No activity yet" in response.text
            # The maneki paw accent (the polished empty state, not a bare <p>).
            assert "luckycat-empty__paw" in response.text


class TestTradeStore:
    """#225: the thread-safe trading store (no app needed)."""

    def setup_method(self) -> None:
        import trade_store
        import wallet

        wallet.reset()
        # Feed must be warmed so ticker prices are populated.
        import feed as feed_mod

        feed_mod.reset()
        trade_store.reset()

    def test_seeded_empty(self) -> None:
        import trade_store

        assert trade_store.positions() == ()
        assert trade_store.open_orders() == ()
        assert trade_store.open_order_count() == 0
        assert trade_store.history() == ()

    def test_buy_debits_wallet_and_books_position(self) -> None:
        import trade_store
        import wallet
        from feed import get_feed

        before = wallet.balance()
        price = get_feed().ticker("PAW-MEOW").price
        # Pick a size whose notional fits the seed balance.
        size = 1.0
        order = trade_store.place_order("PAW-MEOW", "buy", "market", size)
        assert order.status == "filled"
        # Cash debited by the rounded notional.
        assert wallet.balance() == before - round(size * price)
        pos = trade_store.position("PAW-MEOW")
        assert pos is not None
        assert pos.size == size
        # History records the fill.
        assert len(trade_store.history()) == 1

    def test_sell_credits_wallet_and_reduces_position(self) -> None:
        import trade_store
        import wallet

        trade_store.place_order("PAW-MEOW", "buy", "market", 2.0)
        mid = wallet.balance()
        trade_store.place_order("PAW-MEOW", "sell", "market", 2.0)
        # Position fully closed (cleared), wallet credited above the mid.
        assert trade_store.position("PAW-MEOW") is None
        assert wallet.balance() >= mid

    def test_validate_insufficient_balance(self) -> None:
        import trade_store

        # A huge BTC buy can't be covered by the 1000-$MEOW seed.
        errors, _ = trade_store.validate_order("BTC-MEOW", "buy", "market", "10", "")
        assert "size" in errors
        assert any("Not enough $MEOW" in m for m in errors["size"])

    def test_validate_bad_limit_price(self) -> None:
        import trade_store

        errors, _ = trade_store.validate_order("PAW-MEOW", "buy", "limit", "1", "not-a-number")
        assert "limit_price" in errors

    def test_validate_below_min_size(self) -> None:
        import trade_store

        # A tiny DOGE notional falls below the min-notional floor.
        errors, _ = trade_store.validate_order("DOGE-MEOW", "buy", "market", "0.0001", "")
        assert "size" in errors

    def test_open_and_cancel_limit_order(self) -> None:
        import trade_store

        order = trade_store.open_limit_order("SOL-MEOW", "buy", 1.0, 100.0)
        assert trade_store.open_order_count() == 1
        cancelled = trade_store.cancel_order(order.id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"
        assert trade_store.open_order_count() == 0
        # Cancelling an unknown order is a no-op None.
        assert trade_store.cancel_order(9999) is None

    def test_portfolio_value_and_pnl(self) -> None:
        import trade_store
        import wallet

        assert trade_store.portfolio_value() == float(wallet.balance())
        assert trade_store.pnl() == 0.0
        trade_store.place_order("PAW-MEOW", "buy", "market", 1.0)
        # After a buy, value is cash + mark-to-market (>= remaining cash).
        assert trade_store.portfolio_value() >= wallet.balance()


class TestTradePage:
    """#225: GET /trade renders the place-order form + positions + count."""

    async def test_trade_page_renders_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/trade")
            assert response.status == 200
            assert 'id="order-form"' in response.text
            # CSRF protected (hidden field) and posts to the trade route.
            assert 'name="_csrf_token"' in response.text
            assert 'hx-post="/trade/order"' in response.text
            # OOB targets exist in the rendered DOM (fail-loud).
            assert 'id="positions"' in response.text
            assert 'id="open-order-count"' in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text


class TestTradeOrder:
    """#225: POST /trade/order — validation + multi-target OOB fill."""

    async def _csrf_headers(self, client, *, htmx: bool = True) -> dict:
        page = await client.get("/trade")
        cookie = _session_cookie(page)
        csrf = extract_csrf_token(page.text)
        assert csrf is not None
        headers = {"X-CSRF-Token": csrf}
        if htmx:
            headers["HX-Request"] = "true"
        if cookie:
            headers["Cookie"] = f"{_SESSION_COOKIE}={cookie}"
        return headers

    async def test_invalid_order_returns_422_with_field_error(self, example_app) -> None:
        """Insufficient balance -> 422 + re-rendered form with the field error,
        no full-page nav (the order_form block, not the whole page)."""
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post(
                "/trade/order",
                data={"symbol": "BTC-MEOW", "side": "buy", "kind": "market", "size": "10"},
                headers=headers,
            )
            assert response.status == 422
            assert "Not enough $MEOW" in response.text
            # The form re-renders (no full-page <html> shell on a fragment).
            assert 'id="order-form"' in response.text
            assert "<html" not in response.text
            # Submitted values preserved.
            assert "BTC-MEOW" in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_valid_order_single_oob_response(self, example_app) -> None:
        """A fill returns one response with the positions table + open-order count
        + a toast, all OOB swaps, with the form reset as the primary swap. The
        topbar $MEOW balance is NO LONGER an OOB twin here — it is a live `balance`
        SIGNAL: the route emits app.emit('balance', ...) and every binding swaps
        over /_chirp/live, so this response carries no #lucky-cat-balance twin."""
        import wallet

        wallet.reset()
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            before = wallet.balance()
            response = await client.post(
                "/trade/order",
                data={"symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
                headers=headers,
            )
            assert response.status == 200
            # Position row + count + toast, all in one response.
            assert 'id="positions"' in response.text
            assert 'id="position-PAW-MEOW"' in response.text
            assert 'id="open-order-count"' in response.text
            assert "chirpui-toast" in response.text or "Filled" in response.text
            # The balance moved to the live signal — no OOB balance twin in the body.
            assert 'id="lucky-cat-balance"' not in response.text
            # The form re-renders reset (primary swap), and the OOB twins fire.
            assert "hx-swap-oob" in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text
            # The fill debited the wallet (the value the balance signal emits).
            assert wallet.balance() < before

    async def test_order_requires_csrf(self, example_app) -> None:
        """Without a CSRF token the mutating route is rejected (secure-by-default)."""
        async with TestClient(example_app) as client:
            response = await client.post(
                "/trade/order",
                data={"symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
            )
            assert response.status in (400, 403)

    async def test_plain_post_redirects(self, example_app) -> None:
        """A plain (non-htmx) POST gets the FormAction 303 redirect to /trade."""
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client, htmx=False)
            response = await client.post(
                "/trade/order",
                data={"symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
                headers=headers,
            )
            assert_mutation_redirect(response, "/trade")

    async def test_cancel_order_updates_count_and_toast(self, example_app) -> None:
        """Cancelling a resting order OOB-swaps the open-order count + a toast."""
        import trade_store

        order = trade_store.open_limit_order("SOL-MEOW", "buy", 1.0, 100.0)
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post(
                f"/trade/order/{order.id}/cancel",
                data={},
                headers=headers,
            )
            assert response.status == 200
            assert 'id="open-order-count"' in response.text
            assert "cancelled" in response.text.lower()
            assert trade_store.open_order_count() == 0

    async def test_cancel_last_order_oob_swaps_empty_state(self, example_app) -> None:
        """Cancelling the LAST resting order ALSO OOB-swaps the #open-orders-table
        container to the empty-state — so the orders page never shows a bare
        thead (the row deletes itself, but the empty state must appear without a
        reload). Fail-loud: the swap targets a real id that the orders page ships."""
        import trade_store

        order = trade_store.open_limit_order("SOL-MEOW", "buy", 1.0, 100.0)
        async with TestClient(example_app) as client:
            # The orders page ships the #open-orders-table swap target (fail-loud).
            orders_page = await client.get("/portfolio/orders")
            assert 'id="open-orders-table"' in orders_page.text

            headers = await self._csrf_headers(client)
            response = await client.post(
                f"/trade/order/{order.id}/cancel", data={}, headers=headers
            )
            assert response.status == 200
            # The empty-table OOB swap fired, targeting the real container id.
            assert 'id="open-orders-table"' in response.text
            assert "hx-swap-oob" in response.text
            # It carries the empty-state, not a bare table.
            assert "No resting orders" in response.text
            assert trade_store.open_order_count() == 0
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_cancel_non_last_order_no_table_swap(self, example_app) -> None:
        """Cancelling a NON-last order leaves the #open-orders-table untouched
        (the per-row delete handles it) — no wasteful full-table OOB swap; only
        the count badge + toast update."""
        import trade_store

        first = trade_store.open_limit_order("SOL-MEOW", "buy", 1.0, 100.0)
        trade_store.open_limit_order("BTC-MEOW", "sell", 0.5, 90000.0)
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post(
                f"/trade/order/{first.id}/cancel", data={}, headers=headers
            )
            assert response.status == 200
            # Count badge still updates, but the table container does NOT swap.
            assert 'id="open-order-count"' in response.text
            assert 'id="open-orders-table"' not in response.text
            assert trade_store.open_order_count() == 1

    async def test_limit_order_rests_and_bumps_count(self, example_app) -> None:
        """#225 + LOW-1: a LIMIT order rests (no fill, no debit) and bumps the live
        open-order count — wiring the previously-dead resting-limit path through
        the route. A market order fills; a limit order joins the book."""
        import trade_store
        import wallet

        before = wallet.balance()
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post(
                "/trade/order",
                data={
                    "symbol": "PAW-MEOW",
                    "side": "buy",
                    "kind": "limit",
                    "size": "1",
                    "limit_price": "5",
                },
                headers=headers,
            )
            assert response.status == 200
            # Resting toast + the open-order count OOB swap (no position, no debit).
            assert 'id="open-order-count"' in response.text
            assert "Resting" in response.text or "resting" in response.text.lower()
        # The order rested (count bumped), the wallet was NOT debited, and no
        # position was opened — a limit order does not fill in the M2 sim.
        assert trade_store.open_order_count() == 1
        assert wallet.balance() == before
        assert trade_store.position("PAW-MEOW") is None

    async def test_concurrent_buys_never_500(self, example_app) -> None:
        """MEDIUM-bug regression (the free-threading safety proof): hammer many
        concurrent buys that EACH pass validation against the seed balance but
        together far exceed it. The atomic ``try_place_order`` re-checks the
        balance and debits under one lock, so at most a few can clear and the rest
        get a clean **422** — NEVER an unhandled ``ValueError`` 500 (the old
        validate-then-debit race). The wallet must never go negative."""
        import asyncio

        import wallet

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)

            async def buy() -> int:
                # Size 80 PAW-MEOW ≈ 648 $MEOW each: every buy validates against the
                # 1000 seed alone, but two cannot both clear — the loser hits the
                # atomic re-check and gets a 422, not a 500.
                resp = await client.post(
                    "/trade/order",
                    data={
                        "symbol": "PAW-MEOW",
                        "side": "buy",
                        "kind": "market",
                        "size": "80",
                    },
                    headers=headers,
                )
                return resp.status

            statuses = await asyncio.gather(*[buy() for _ in range(12)])

        # Every response is a clean fill (200/303) or a clean rejection (422) —
        # never a 500. This is the whole point of the showcase.
        assert all(s in (200, 303, 422) for s in statuses), statuses
        assert 500 not in statuses
        # At least one buy cleared and at least one was rejected (the race fired).
        assert any(s in (200, 303) for s in statuses), statuses
        assert any(s == 422 for s in statuses), statuses
        # The wallet never went negative (no double-spend).
        assert wallet.balance() >= 0

    def test_try_place_order_is_atomic_under_threads(self) -> None:
        """The store-level atomicity proof: fire concurrent buys from real threads
        and assert the wallet never goes negative and the number of fills never
        exceeds what the balance can cover. ``try_place_order`` never raises — a
        racing buy that no longer fits returns ``(None, errors)``."""
        import threading

        import trade_store
        import wallet
        from feed import get_feed

        wallet.reset()
        trade_store.reset()
        # Each buy costs ~648 $MEOW; only one of these can clear against 1000.
        price = get_feed().ticker("PAW-MEOW").price
        size = 80.0
        results: list[tuple[object, dict]] = []
        results_lock = threading.Lock()

        def worker() -> None:
            out = trade_store.try_place_order(
                "PAW-MEOW", "buy", "market", size, None, fill_price=price
            )
            with results_lock:
                results.append(out)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        fills = [o for o, _ in results if o is not None]
        rejects = [errs for o, errs in results if o is None]
        # No exception escaped (every result is a clean (order|None, errors)).
        assert len(results) == 16
        # The wallet never went negative.
        assert wallet.balance() >= 0
        # Only as many fills as the balance covers cleared; the rest were rejected.
        assert len(fills) >= 1
        assert len(rejects) >= 1
        assert all("size" in errs for errs in rejects)


class TestNavModel:
    """#231: the pure-Python server nav model (no app needed)."""

    def test_route_state_active_rooms(self) -> None:
        from navigation import route_state

        assert route_state("/").active_room == "markets"
        assert route_state("/markets").active_room == "markets"
        assert route_state("/markets/BTC-MEOW").active_room == "markets"
        assert route_state("/portfolio").active_room == "portfolio"
        assert route_state("/portfolio/orders").active_room == "portfolio"
        assert route_state("/trade").active_room == "trade"
        assert route_state("/activity/deposits").active_room == "activity"
        assert route_state("/settings/security").active_room == "settings"

    def test_market_detail_state(self) -> None:
        from navigation import route_state

        s = route_state("/markets/BTC-MEOW")
        assert s.market_detail_active is True
        assert s.current_symbol == "BTC-MEOW"
        # The markets *index* is not a detail route.
        assert route_state("/markets").market_detail_active is False
        # Queryless + fragmentless normalization.
        assert route_state("/markets/ETH-MEOW?tab=book#x").current_symbol == "ETH-MEOW"

    def test_shell_navigation_prunes_empty_and_dispatches(self) -> None:
        from feed import SimFeed
        from navigation import route_state, shell_navigation

        feed = SimFeed(seed=1)
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}

        # Icon rail is the five persistent rooms, regardless of route.
        nav = shell_navigation(route_state("/"), markets=markets, tickers=tickers)
        assert tuple(i.key for i in nav.primary_items) == (
            "markets",
            "portfolio",
            "trade",
            "activity",
            "settings",
        )
        # Markets room: a market list section with signed-pct badges.
        market_section = next(s for s in nav.sidebar_sections if s.key == "markets")
        assert len(market_section.items) == len(markets)
        assert any(i.badge for i in market_section.items)

        # Portfolio room dispatches to its own sections (no markets list).
        pnav = shell_navigation(route_state("/portfolio"), markets=markets, tickers=tickers)
        assert {s.key for s in pnav.sidebar_sections} == {"portfolio"}
        # No empty sections survive pruning.
        assert all(s.items for s in pnav.sidebar_sections)


class TestProgressiveRail:
    """#231: the two-tier rail in the rendered shell."""

    async def test_both_rails_render_on_landing(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            # Outer icon rail + inner contextual rail, inside the OOB target.
            assert "luckycat-primary-rail" in response.text
            assert "luckycat-inner-rail" in response.text
            assert 'id="chirpui-sidebar-nav"' in response.text
            # Icon-only rail carries a tooltip + accessible label.
            assert "data-rail-tooltip" in response.text
            assert 'aria-label="Markets"' in response.text
            # hx-sync coalesces rapid boosted nav clicks.
            assert 'hx-sync="#main:replace"' in response.text

    async def test_icon_rail_persists_across_routes(self, example_app) -> None:
        """The five rooms appear on every route (markets / detail / a new room)."""
        async with TestClient(example_app) as client:
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/settings"):
                response = await client.get(path)
                assert response.status == 200, path
                for label in ("Markets", "Portfolio", "Trade", "Activity", "Settings"):
                    assert f'aria-label="{label}"' in response.text, (path, label)

    @staticmethod
    def _active_room_hrefs(html: str) -> set[str]:
        """The hrefs of every icon-rail link rendered with the active class."""
        import re

        return {
            m.group(1)
            for m in re.finditer(
                r'luckycat-primary-rail__link--active"\s+href="([^"]+)"',
                html,
            )
        }

    async def test_icon_rail_active_state_is_per_room(self, example_app) -> None:
        async with TestClient(example_app) as client:
            home = await client.get("/")
            # On /, exactly the Markets room (href="/") is active.
            assert self._active_room_hrefs(home.text) == {"/"}

            pf = await client.get("/portfolio")
            # Active marker moves to Portfolio, and only Portfolio.
            assert self._active_room_hrefs(pf.text) == {"/portfolio"}

            st = await client.get("/settings")
            # The Settings room lights up, and only Settings.
            assert self._active_room_hrefs(st.text) == {"/settings"}

            detail = await client.get("/markets/BTC-MEOW")
            # A market-detail route stays in the Markets room (path-prefix).
            assert self._active_room_hrefs(detail.text) == {"/"}

    async def test_inner_rail_changes_by_route(self, example_app) -> None:
        async with TestClient(example_app) as client:
            markets = await client.get("/")
            # Markets room → market list + filter lane (Watchlist + All markets;
            # the old cosmetic Gainers/Losers no-op lanes were removed).
            assert "Filters" in markets.text
            assert "All markets" in markets.text

            detail = await client.get("/markets/BTC-MEOW")
            # Market-detail room → a "this market" lane (book / trades / info).
            assert "Order book" in detail.text
            assert "Overview" in detail.text

            portfolio = await client.get("/portfolio")
            # Portfolio room → holdings / open orders / history; no filter lane.
            assert "Holdings" in portfolio.text
            assert "Open orders" in portfolio.text
            assert "All markets" not in portfolio.text

    async def test_market_links_carry_change_badge(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            # Signed 24h-change pill on the inner-rail market links.
            assert "luckycat-inner-rail__badge" in response.text
            assert "%" in response.text

    async def test_sidebar_brand_present_balance_is_topbar_only(self, example_app) -> None:
        """The inner-rail header shows the brand. The $MEOW balance is GLOBAL
        state, so it is NOT duplicated in the rail footer — it renders once in
        the topbar (IA doctrine; the rail copy also overflowed the column)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "luckycat-inner-rail__brand" in response.text
            # No rail-footer balance copy.
            assert "luckycat-inner-rail__balance" not in response.text
            # The single balance lives in the topbar token, still in $MEOW.
            assert "luckycat-token__amount" in response.text
            assert "$MEOW" in response.text

    async def test_boosted_nav_swaps_inner_rail_via_oob(self, example_app) -> None:
        """Boosted navigation returns a single sidebar_oob chunk targeting
        #chirpui-sidebar-nav with the new room's contextual sections (#231)."""
        async with TestClient(example_app) as client:
            response = await client.get(
                "/portfolio",
                headers={"HX-Request": "true", "HX-Boosted": "true", "HX-Target": "main"},
            )
            assert response.status == 200
            # The OOB chunk wraps the rail under the chirp-ui sidebar target.
            assert 'id="chirpui-sidebar-nav"' in response.text
            assert "hx-swap-oob" in response.text
            # And it carries the Portfolio room's contextual content.
            oob = response.text[response.text.find('id="chirpui-sidebar-nav"') :]
            assert "Holdings" in oob
            assert "luckycat-primary-rail__link--active" in oob
            # No raw template tags leak into the boosted response.
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_room_stubs_render_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            for path, heading in (
                ("/portfolio", "Portfolio"),
                ("/trade", "Trade"),
                ("/activity", "Activity"),
                ("/settings", "Settings"),
            ):
                response = await client.get(path)
                assert response.status == 200, path
                assert "<html" in response.text
                assert heading in response.text
                # Shell chrome composes in (topbar balance + ticker).
                assert "$MEOW" in response.text
                assert "{{" not in response.text
                assert "{%" not in response.text


class TestMobileShell:
    """Mobile/responsive pass: the hamburger + nav drawer that replace the inline
    two-tier rail and the crammed topbar shell-actions on narrow viewports.

    The visual stacking itself is CSS (all behind a ``max-width: 48rem`` media
    query so desktop is unchanged), which a string-asserting TestClient cannot
    measure — that is the browser smoke's job (``test_browser_smoke.py``). What
    this class locks down is the *markup contract* the CSS keys off:

      * a mobile hamburger trigger that drives the ``#lucky-cat-nav`` drawer via
        the same ``chirpuiDialogTarget`` controller chirp-ui's ``drawer_trigger``
        uses;
      * a nav drawer whose body reuses the SAME ``shell_navigation`` model as the
        inline rail (the rooms + the route-context sections), with the boosted
        shell-outlet contract and close-on-click;
      * the drawer carries NO duplicate ``#chirpui-sidebar-nav`` id (that id is the
        inline rail's OOB target and must stay unique, or the boosted-nav OOB swap
        breaks);
      * the drawer is rendered once in the persistent topbar shell (every route),
        so it survives boosted navigation.
    """

    async def test_hamburger_trigger_targets_nav_drawer(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            html = response.text
            # The hamburger button + its accessible name + the drawer-target hook.
            assert "luckycat-nav-trigger" in html
            assert 'aria-label="Open navigation menu"' in html
            assert 'data-dialog-target="lucky-cat-nav"' in html
            # The drawer dialog it opens (chirp-ui native <dialog closedby="any">).
            assert 'id="lucky-cat-nav"' in html
            assert "chirpui-drawer" in html

    async def test_nav_drawer_reuses_rail_model_with_boosted_contract(self, example_app) -> None:
        """The drawer lists the five rooms + the route-context sections, each link
        carrying the boosted shell outlet + close-on-click, all from the same
        navigation model as the inline rail."""
        import re

        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 200
            match = re.search(r"luckycat-nav-drawer__nav.*?</nav>", response.text, re.S)
            assert match is not None, "nav drawer body did not render"
            drawer = match.group(0)
            # All five rooms (the outer icon rail, here as labelled rows).
            for label in ("Markets", "Portfolio", "Trade", "Activity", "Settings"):
                assert f">{label}</span>" in drawer, label
            # The Portfolio room's route-context sub-nav is present in the drawer.
            assert "/portfolio/orders" in drawer
            assert "/portfolio/history" in drawer
            # Active room is server-marked (agrees with syncNav()).
            assert "luckycat-nav-drawer__link--active" in drawer
            assert 'aria-current="page"' in drawer
            # Boosted shell-outlet contract + rapid-click coalescing on the links.
            assert 'hx-sync="#main:replace"' in drawer
            assert 'hx-target="#main"' in drawer
            # The drawer dismisses itself as navigation starts.
            assert "closest('dialog')" in drawer

    async def test_nav_drawer_shows_watchlist_count(self, example_app) -> None:
        """The mobile drawer's Watchlist lane shows its starred-count badge — the
        layout threads watchlist_count through mobile_drawer_nav so the drawer
        does not silently drop the count the desktop rail shows."""
        import re

        import watchlist

        watchlist.add("BTC-MEOW")
        watchlist.add("SOL-MEOW")
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            match = re.search(r"luckycat-nav-drawer__nav.*?</nav>", response.text, re.S)
            assert match is not None
            drawer = match.group(0)
            # The Watchlist lane is present with its count badge (2 starred).
            assert "/watchlist" in drawer
            # The drawer renders item.count via the chirp-ui sidebar badge.
            wl = drawer[drawer.find("/watchlist") :]
            badge = re.search(r'class="chirpui-sidebar__badge[^"]*">\s*2\s*<', wl)
            assert badge is not None, "drawer watchlist count badge missing"

    async def test_nav_drawer_does_not_duplicate_rail_oob_id(self, example_app) -> None:
        """#chirpui-sidebar-nav is the inline rail's OOB target — it must appear
        exactly once. A duplicate (e.g. if the drawer reused the rail wholesale)
        would break the boosted-nav OOB swap."""
        async with TestClient(example_app) as client:
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/settings"):
                response = await client.get(path)
                assert response.status == 200, path
                assert response.text.count('id="chirpui-sidebar-nav"') == 1, path
                assert response.text.count('id="lucky-cat-nav"') == 1, path

    async def test_nav_drawer_persists_across_routes(self, example_app) -> None:
        """The drawer ships on every route (it lives in the persistent topbar
        shell), so the hamburger works no matter where boosted nav landed."""
        async with TestClient(example_app) as client:
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/trade", "/settings"):
                response = await client.get(path)
                assert response.status == 200, path
                assert "luckycat-nav-trigger" in response.text, path
                assert 'id="lucky-cat-nav"' in response.text, path

    async def test_market_detail_stacks_book_and_tape(self, example_app) -> None:
        """The order book + trade tape both render in the detail grid the mobile
        media query stacks to a single column."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/BTC-MEOW")
            assert response.status == 200
            assert "luckycat-detail__grid" in response.text
            assert 'id="order-book"' in response.text
            assert 'id="trade-tape"' in response.text


class TestRailCollapse:
    """#231 part 2 (BUILD 1): the rail-edge resize handle + the cookie-persisted,
    server-side-first collapse state.

    The rail-edge handle (``.luckycat-sidebar-resize``, ``role="separator"``,
    ``cursor: ew-resize``) replaces the old click-toggle button — BUILD 1 ships
    the handle ELEMENT + ARIA; BUILD 2 wires the genuine continuous pointer-drag
    resize + double-click collapse. The collapse preference is preserved: it
    rides a namespaced cookie (``luckycat_rail_collapsed``) read server-side so
    the first paint is already collapsed (no FOUC). The layout pre-renders a
    cookie-gated ``<style>`` the shell JS then disables.
    """

    _COOKIE = "luckycat_rail_collapsed"

    async def test_resize_handle_renders_in_rail(self, example_app) -> None:
        """The resize handle ships INSIDE the rail (so it survives OOB swaps),
        carries the separator ARIA + drag hook, and the shell script is wired.
        The discoverability follow-up ALSO ships a visible collapse-toggle button
        (the drag handle is kept too — they coexist)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            # The genuine drag-resize handle.
            assert "luckycat-sidebar-resize" in response.text
            assert "data-luckycat-rail-resize" in response.text
            assert 'role="separator"' in response.text
            assert 'aria-orientation="vertical"' in response.text
            # The visible, discoverable collapse-toggle button is now present.
            assert "data-luckycat-rail-toggle" in response.text
            # The shell script is wired (defer, from /static).
            assert 'src="/static/lucky-cat-shell.js"' in response.text

    async def test_visible_collapse_toggle_is_accessible(self, example_app) -> None:
        """The discoverable collapse control is a real, accessible <button>:
        aria-expanded (default expanded → "true"), aria-controls pointing at the
        navigation region, and an accessible label. It ships TWICE — an
        always-reachable copy on the icon rail (to re-expand when collapsed) and
        one in the inner-rail header — so the toggle survives a collapse."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            text = response.text
            # A real button (not a div) so Enter/Space work natively.
            assert "luckycat-rail-toggle" in text
            assert 'aria-expanded="true"' in text
            assert 'aria-controls="chirpui-sidebar-nav"' in text
            # Accessible label present (the JS flips it to "Expand" when collapsed).
            assert "Collapse navigation" in text
            # Two placements: icon-rail copy (reachable when collapsed) + inner-rail.
            assert "luckycat-rail-toggle--icon" in text
            assert "luckycat-rail-toggle--inner" in text

    async def test_collapse_toggle_survives_boosted_oob_swap(self, example_app) -> None:
        """The visible toggle re-ships in the boosted sidebar OOB chunk so it is
        never lost across navigation (like the resize handle)."""
        async with TestClient(example_app) as client:
            response = await client.get(
                "/portfolio",
                headers={"HX-Request": "true", "HX-Boosted": "true", "HX-Target": "main"},
            )
            assert response.status == 200
            oob = response.text[response.text.find('id="chirpui-sidebar-nav"') :]
            assert "data-luckycat-rail-toggle" in oob

    async def test_default_is_expanded_no_precollapse_style(self, example_app) -> None:
        """With no cookie the rail renders expanded — the pre-collapse <style>
        gate is absent and the handle seeds the expanded width on aria-valuenow."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'id="luckycat-rail-cookie-state"' not in response.text
            # Expanded → the handle seeds the mid (expanded) width.
            assert 'aria-valuenow="256"' in response.text

    async def test_collapsed_cookie_pre_renders_collapsed_state(self, example_app) -> None:
        """The headline no-FOUC guarantee: a collapsed cookie makes the SERVER
        emit the pre-collapse <style> + seed the collapsed width on first paint."""
        async with TestClient(example_app) as client:
            response = await client.get("/", headers={"Cookie": f"{self._COOKIE}=true"})
            assert response.status == 200
            # Server-rendered pre-collapse <style> (keyed on the cookie, no FOUC).
            assert 'id="luckycat-rail-cookie-state"' in response.text
            # It collapses the shell sidebar column to the icon-rail width.
            assert "--chirpui-sidebar-width: var(--luckycat-icon-rail-width" in response.text
            # Collapsed → aria-valuenow seeds at the min (it must stay within
            # valuemin/valuemax; collapse is conveyed by the shell class, not a
            # sub-min value).
            assert 'aria-valuenow="176"' in response.text

    async def test_expanded_cookie_renders_expanded(self, example_app) -> None:
        """An explicit ``false`` cookie is treated as expanded (round-trip)."""
        async with TestClient(example_app) as client:
            response = await client.get("/", headers={"Cookie": f"{self._COOKIE}=false"})
            assert response.status == 200
            assert 'id="luckycat-rail-cookie-state"' not in response.text
            assert 'aria-valuenow="256"' in response.text

    async def test_collapse_state_survives_boosted_oob_swap(self, example_app) -> None:
        """The resize handle re-ships in the boosted sidebar OOB chunk so it is
        never lost across navigation."""
        async with TestClient(example_app) as client:
            response = await client.get(
                "/portfolio",
                headers={
                    "HX-Request": "true",
                    "HX-Boosted": "true",
                    "HX-Target": "main",
                    "Cookie": f"{self._COOKIE}=true",
                },
            )
            assert response.status == 200
            oob = response.text[response.text.find('id="chirpui-sidebar-nav"') :]
            assert "data-luckycat-rail-resize" in oob
            # The OOB rail re-render reflects the collapsed preference; aria-valuenow
            # stays clamped to the min (valuemin) rather than a sub-min value.
            assert 'aria-valuenow="176"' in oob

    def test_rail_is_collapsed_reads_cookie(self) -> None:
        """The server reader is pure: no request in scope → expanded default."""
        from shell import RAIL_COLLAPSED_COOKIE, rail_is_collapsed

        assert RAIL_COLLAPSED_COOKIE == "luckycat_rail_collapsed"
        # No request in the ContextVar → safe default (expanded).
        assert rail_is_collapsed() is False

    _WIDTH_COOKIE = "luckycat_rail_width"

    async def test_dragged_width_cookie_pre_sizes_rail(self, example_app) -> None:
        """BUILD 2 no-flash width guarantee: a persisted drag width makes the
        SERVER emit a pre-sized `--luckycat-rail-width` <style> and seed the
        handle's aria-valuenow on first paint (no JS-only width flash)."""
        async with TestClient(example_app) as client:
            response = await client.get("/", headers={"Cookie": f"{self._WIDTH_COOKIE}=240"})
            assert response.status == 200
            assert 'id="luckycat-rail-cookie-state"' in response.text
            assert "--luckycat-rail-width: 240px" in response.text
            # The handle seeds the persisted width for screen-reader resize state.
            assert 'aria-valuenow="240"' in response.text

    async def test_dragged_width_cookie_is_clamped_not_reflected_raw(self, example_app) -> None:
        """SECURITY: the width cookie is reflected into a server <style>, so it is
        parsed+clamped — an out-of-range value clamps and a non-numeric/injection
        value is rejected (never echoed into CSS)."""
        async with TestClient(example_app) as client:
            # Out-of-range → clamped to the max (416), not the raw 99999.
            clamped = await client.get("/", headers={"Cookie": f"{self._WIDTH_COOKIE}=99999"})
            assert "--luckycat-rail-width: 416px" in clamped.text
            assert "99999" not in clamped.text
            # Non-numeric / CSS-breakout attempt → rejected: no pre-sized style, and
            # the raw payload never reaches the response.
            attack = "1px}</style><script>alert(1)</script>"
            evil = await client.get("/", headers={"Cookie": f"{self._WIDTH_COOKIE}={attack}"})
            assert "</style><script>alert(1)</script>" not in evil.text
            assert "--luckycat-rail-width: 1px" not in evil.text

    def test_rail_width_reader_clamps_and_rejects(self) -> None:
        """The server width reader is pure + bounded: no request → None; valid →
        clamped int; out-of-range → clamped; non-numeric → None."""
        from shell import (
            RAIL_WIDTH_COOKIE,
            RAIL_WIDTH_MAX_PX,
            RAIL_WIDTH_MIN_PX,
            rail_width,
        )

        assert RAIL_WIDTH_COOKIE == "luckycat_rail_width"
        # No request in the ContextVar → safe default (None → CSS default width).
        assert rail_width() is None

        class _Req:
            def __init__(self, value):
                self.cookies = {} if value is None else {RAIL_WIDTH_COOKIE: value}

        assert rail_width(_Req("240")) == 240
        assert rail_width(_Req("10")) == RAIL_WIDTH_MIN_PX
        assert rail_width(_Req("9999")) == RAIL_WIDTH_MAX_PX
        assert rail_width(_Req("not-a-number")) is None
        assert rail_width(_Req(None)) is None


class TestPortfolioDashboard:
    """#224: GET /portfolio is a Suspense dashboard — shell paints instantly with
    skeletons, then six deferred panels stream in as OOB swaps."""

    async def test_shell_renders_all_panel_targets(self, example_app) -> None:
        """The shell ships every deferred panel's DOM id (the OOB swap targets
        must exist — fail-loud) plus skeleton placeholders."""
        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 200
            assert "<html" in response.text
            for dom_id in (
                "portfolio-value",
                "holdings",
                "allocation",
                "open-orders",
                "activity-feed",
                "ft-panel",
            ):
                assert f'id="{dom_id}"' in response.text, dom_id
            # The #225 trade-flow OOB count target also lives on this page.
            assert 'id="open-order-count"' in response.text
            # Skeleton loading affordance shipped in the shell.
            assert "luckycat-skel" in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_empty_account_resolves_to_empty_state_not_skeleton(self, example_app) -> None:
        """The headline `is deferred` correctness proof: with zero positions the
        deferred `holdings` resolves to an EMPTY tuple, which must render the
        empty-state — NOT a perpetual skeleton. (`is not none` would take the
        loaded branch against the DEFERRED sentinel / fail to distinguish empty
        from loading; `is deferred` is what makes the empty tuple show the
        empty state.)"""
        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 200
            # Deferred blocks have streamed in: the empty holdings state shows.
            assert "No holdings yet" in response.text
            # And the all-cash allocation empty branch resolved too.
            assert "All cash" in response.text

    async def test_value_reflects_seed_wallet(self, example_app) -> None:
        """With no positions, portfolio value == the seed $MEOW wallet balance."""
        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 200
            # Seed wallet (INITIAL_MEOW=1000), zero P&L, all cash.
            assert "1000" in response.text
            assert "$MEOW" in response.text
            assert "unrealized" in response.text.lower()

    async def test_holdings_render_after_a_fill(self, example_app) -> None:
        """A booked position shows up in the deferred holdings table (loaded
        branch), proving the empty-vs-loaded distinction works both ways."""
        import trade_store

        trade_store.place_order("PAW-MEOW", "buy", "market", 1.0)
        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 200
            # The position taped into the holdings table (not the empty state).
            assert "PAW-MEOW" in response.text
            assert "No holdings yet" not in response.text

    async def test_deferred_panels_swap_to_existing_dom_ids(self, example_app) -> None:
        """HIGH-bug regression: every deferred panel must OOB-swap to a DOM id that
        EXISTS in the shell (fail-loud). On a browser GET the Suspense stream uses
        the script-based defer formatter (``_chirp_d_<target>`` + a
        ``getElementById(<target>)`` swap); the target MUST be the section's
        hyphenated DOM id, not the underscore block name. ``portfolio_value`` (the
        block) targets ``#portfolio-value`` (the section) only because page.py's
        ``defer_map`` remaps it — an un-remapped block would target
        ``getElementById("portfolio_value")`` (no such element) and the value+P&L
        panel would stay a skeleton forever."""
        import re

        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 200
            text = response.text
            # The script-defer swaps: (template-id, target-id) pairs.
            pairs = dict(
                re.findall(
                    r'getElementById\("_chirp_d_([^"]+)"\),'
                    r'e=document\.getElementById\("([^"]+)"\)',
                    text,
                )
            )
            # All five deferred panels stream a swap, each targeting its section id.
            for dom_id in (
                "portfolio-value",
                "holdings",
                "allocation",
                "open-orders",
                "activity-feed",
            ):
                assert dom_id in pairs, f"no deferred swap for {dom_id}: {sorted(pairs)}"
                assert pairs[dom_id] == dom_id
                # The shell ships that id as the swap target (fail-loud).
                assert f'id="{dom_id}"' in text, dom_id
            # The HIGH bug's fingerprint must be gone: no underscore block-name
            # target leaks into the stream.
            assert "portfolio_value" not in text

    async def test_deferred_panels_render_no_duplicate_ids_htmx(self, example_app) -> None:
        """LOW-2 de-dup: on the htmx OOB path each deferred panel emits a wrapper
        ``<div id="X" hx-swap-oob="true">`` (an outerHTML swap against the shell's
        same-id element). The inner ``<section>`` therefore must NOT also carry the
        id — otherwise the post-swap DOM would hold two same-id nodes. The id lives
        on the shell section (swap target) and the OOB wrapper (swap source); the
        inner section in the OOB chunk drops it."""
        import re

        async with TestClient(example_app) as client:
            response = await client.get("/portfolio", headers={"HX-Request": "true"})
            assert response.status == 200
            text = response.text
            wrappers = {
                m.group(1) for m in re.finditer(r'<div id="([^"]+)" hx-swap-oob="true">', text)
            }
            for dom_id in (
                "portfolio-value",
                "holdings",
                "allocation",
                "open-orders",
                "activity-feed",
            ):
                assert dom_id in wrappers, f"no OOB wrapper for {dom_id}"
                # Exactly two occurrences: the shell section (target) + the OOB
                # wrapper div (source). The inner section dropped its id, so the
                # swapped DOM never holds a duplicate.
                assert text.count(f'id="{dom_id}"') == 2, dom_id


class TestFreeThreadingPanel:
    """#227 Part A: the visible free-threading proof panel + its live SSE twin."""

    async def test_panel_renders_honest_gil_and_pool_facts(self, example_app) -> None:
        """The portfolio shell ships the FT panel with the real GIL state and the
        worker-pool width (genuine, not faked)."""
        import sys

        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 200
            assert 'id="ft-panel"' in response.text
            assert "Free-threading" in response.text
            assert "GIL" in response.text
            # Honest: the panel reflects this interpreter's actual GIL state.
            gil_on = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
            assert ("enabled ✗" in response.text) is gil_on
            assert ("disabled ✓" in response.text) is (not gil_on)
            # The live channel is wired (sse-connect to the FT stream).
            assert 'sse-connect="/ft/stream"' in response.text

    async def test_ft_stream_is_oob_event_stream(self, example_app) -> None:
        """/ft/stream pushes OOB fragments targeting #ft-panel each tick window."""
        async with TestClient(example_app) as client:
            result = await client.sse("/ft/stream", max_events=3)
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        joined = "".join(e.data for e in result.events if e.data)
        # Fail-loud OOB: the swap target matches the full-page DOM id.
        assert 'id="ft-panel"' in joined
        assert "hx-swap-oob" in joined
        # A ticks/sec figure is reported.
        assert "Ticks / sec" in joined
        # The streamed twin also carries the honest pool facts (not just the rate).
        assert "Worker threads" in joined
        assert "Markets / tick" in joined
        assert "{{" not in joined
        assert "{%" not in joined

    async def test_ft_stream_reports_genuine_nonzero_rate(self, example_app) -> None:
        """Acceptance: ticks/sec reflects genuine parallel tick computation, not a
        sleep. The figure is a real number derived from the SimFeed tick counter
        advancing across the worker pool — so at least one streamed window must
        report a positive rate (the engine fanned ticks out and the counter moved).
        """
        import re

        async with TestClient(example_app) as client:
            result = await client.sse("/ft/stream", max_events=4)
        joined = "".join(e.data for e in result.events if e.data)
        rates = re.findall(r"Ticks / sec</dt>\s*<dd>\s*([0-9.]+)", joined)
        # A real numeric figure rendered (not the "…" placeholder, not a tag).
        assert rates, f"no numeric ticks/sec figure in stream: {joined[:400]!r}"
        # Genuine work: the counter advanced, so some window is strictly positive.
        assert any(float(v) > 0 for v in rates), rates

    def test_ft_panel_facts_are_honest_not_hardcoded(self) -> None:
        """The panel's pool facts come from the live SimFeed, not magic numbers:
        worker_count == the fan-out pool width and market_count == the markets it
        advances per tick. (Asserting equality, not a literal, keeps the test
        honest if the market set changes.)"""
        from feed import SimFeed

        feed = SimFeed(seed=1)
        assert feed.market_count == len(feed.markets())
        # The pool is bounded to at least the market count (genuine parallel width).
        assert feed.worker_count >= feed.market_count
        assert feed.worker_count >= 2


class TestTickCounter:
    """#227 Part A: the observability-only tick counter is honest and never
    perturbs the deterministic price engine."""

    def test_counter_advances_with_ticks(self) -> None:
        import asyncio

        from feed import SimFeed

        feed = SimFeed(seed=1, tick_interval=0)
        assert feed.tick_count() == 0
        symbol = feed.markets()[0].symbol

        async def drive() -> None:
            agen = feed.subscribe(symbol)
            for _ in range(5):
                await agen.__anext__()
            await agen.aclose()

        asyncio.run(drive())
        # Every symbol advances per tick → 5 ticks * market_count symbol-advances.
        assert feed.tick_count() == 5 * feed.market_count
        assert feed.worker_count >= 2

    def test_counter_does_not_perturb_determinism(self) -> None:
        """Reading the counter must not change the seed→tick sequence."""
        import asyncio

        from feed import SimFeed

        async def run_one(read_counter: bool) -> list:
            feed = SimFeed(seed=0xCA7, tick_interval=0)
            symbol = feed.markets()[0].symbol
            agen = feed.subscribe(symbol)
            seq = []
            for _ in range(12):
                tick = await agen.__anext__()
                if read_counter:
                    _ = feed.tick_count()  # observe — must be inert
                seq.append(tick.ticker.price)
            await agen.aclose()
            return seq

        with_reads = asyncio.run(run_one(True))
        without_reads = asyncio.run(run_one(False))
        assert with_reads == without_reads

    def test_reset_zeroes_counter(self) -> None:
        import asyncio

        from feed import SimFeed

        feed = SimFeed(seed=1, tick_interval=0)

        async def drive() -> None:
            agen = feed.subscribe(feed.markets()[0].symbol)
            for _ in range(3):
                await agen.__anext__()
            await agen.aclose()

        asyncio.run(drive())
        assert feed.tick_count() > 0
        feed.reset()
        assert feed.tick_count() == 0


class TestNotificationsStore:
    """The thread-safe notifications log behind the topbar bell (no app needed)."""

    def setup_method(self) -> None:
        import notifications

        notifications.reset()

    def test_seeded_empty(self) -> None:
        import notifications

        assert notifications.recent() == ()
        assert notifications.unread_count() == 0
        assert notifications.latest_id() == 0

    def test_append_bumps_unread_and_is_newest_first(self) -> None:
        import notifications

        first = notifications.add("deposit", "Deposited 100 $MEOW", "balance now 1100")
        second = notifications.add("fill", "Filled buy 1 PAW-MEOW")
        # Monotonic ids; newest first in the feed.
        assert second.id == first.id + 1
        feed = notifications.recent()
        assert tuple(n.id for n in feed) == (second.id, first.id)
        # Both are unread until read.
        assert notifications.unread_count() == 2
        assert notifications.latest_id() == second.id

    def test_mark_all_read_clears_then_relights_on_new(self) -> None:
        import notifications

        notifications.add("fill", "A")
        notifications.add("fill", "B")
        assert notifications.unread_count() == 2
        assert notifications.mark_all_read() == 0
        assert notifications.unread_count() == 0
        # A later arrival re-lights the badge (above the new watermark).
        notifications.add("price", "BTC-MEOW ▲ +2.00%")
        assert notifications.unread_count() == 1

    def test_drain_since_returns_newer_oldest_first(self) -> None:
        import notifications

        a = notifications.add("fill", "A")
        b = notifications.add("fill", "B")
        c = notifications.add("fill", "C")
        # Everything after a, oldest first (the SSE prepend order).
        drained = notifications.drain_since(a.id)
        assert tuple(n.id for n in drained) == (b.id, c.id)
        # Nothing new past the head.
        assert notifications.drain_since(c.id) == ()

    def test_reset_clears_log_and_counters(self) -> None:
        import notifications

        notifications.add("fill", "A")
        notifications.mark_all_read()
        notifications.reset()
        assert notifications.recent() == ()
        assert notifications.unread_count() == 0
        assert notifications.latest_id() == 0
        # Ids restart from 1 after reset (deterministic test isolation).
        assert notifications.add("fill", "fresh").id == 1

    def test_log_is_bounded(self) -> None:
        import notifications

        for i in range(120):
            notifications.add("price", f"tick {i}")
        # Ring trims to _MAX_LOG; the newest entry is still on top.
        assert len(notifications.recent(limit=1000)) == notifications._MAX_LOG
        assert notifications.recent()[0].title == "tick 119"

    def test_append_is_atomic_under_threads(self) -> None:
        """Free-threading safety: many threads append concurrently and every id is
        unique + the log holds exactly _MAX_LOG (no lost/duplicate writes)."""
        import threading

        import notifications

        def worker(n: int) -> None:
            for i in range(50):
                notifications.add("fill", f"t{n}-{i}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        feed = notifications.recent(limit=10_000)
        # Bounded ring keeps the newest _MAX_LOG; the ids it holds are all distinct.
        assert len(feed) == notifications._MAX_LOG
        ids = [n.id for n in feed]
        assert len(set(ids)) == len(ids)


class TestNotificationsBell:
    """The topbar bell + unread badge + dropdown feed render in the persistent
    shell, folded onto the ONE /_chirp/live signal connection: the bell's sinks
    are EXISTING elements carrying manual sse-swap bindings (notifications /
    notif_badge / notif_announce), not a separate SSE scope or OOB twins."""

    _SESSION_COOKIE = "chirp_session_lucky_cat"

    async def test_bell_renders_in_shell(self, example_app) -> None:
        """The bell, its (empty) badge sink, the dropdown list sink, and the
        single /_chirp/live signal connection ship on the landing page."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            html = response.text
            # The bell trigger + its badge sink + the dropdown list sink.
            assert 'id="notif-bell"' in html
            assert 'id="notif-badge"' in html
            assert 'id="notif-list"' in html
            assert 'aria-label="Notifications"' in html
            # The bell rides the SINGLE merged signal connection — the old separate
            # /notifications/stream scope is gone (the N→1 fold).
            assert 'sse-connect="/_chirp/live' in html
            assert 'sse-connect="/notifications/stream"' not in html
            # The bell's three sinks are manual sse-swap bindings on the existing
            # elements (NOT signal_block() wrappers): list / badge / announce.
            assert 'sse-swap="notifications"' in html
            assert 'sse-swap="notif_badge"' in html
            assert 'sse-swap="notif_announce"' in html
            # Seed state is empty: no unread pill, the empty-state copy shows.
            assert "luckycat-notif-badge" not in html
            assert "No notifications yet" in html
            assert "{{" not in html
            assert "{%" not in html

    async def test_bell_seeds_list_and_badge_from_signals(self, example_app) -> None:
        """SSR seeding: with notifications on record, the #notif-list sink paints
        the recent rows and the #notif-badge sink paints the unread pill on the
        FIRST render (no empty-then-fill flash), seeded from the signal renders."""
        import re

        import notifications

        notifications.add("fill", "Filled buy 1 PAW-MEOW", "@ 8 MEOW.")
        notifications.add("deposit", "Deposited 250 $MEOW", "Balance now 1250 $MEOW.")
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
        # The list sink is SSR-seeded with the rows (inside the bound <ul>).
        ul = html[html.find('id="notif-list"') :]
        assert 'sse-swap="notifications"' in ul[: ul.find("</ul>") + 5]
        assert "Filled buy 1 PAW-MEOW" in ul
        assert "Deposited 250 $MEOW" in ul
        # The badge sink is SSR-seeded with the unread count pill (the "2").
        badge = re.search(r'<span id="notif-badge"[^>]*>(.*?)</span>', html, re.DOTALL)
        assert badge is not None
        assert 'sse-swap="notif_badge"' in badge.group(0)
        assert "luckycat-notif-badge" in badge.group(1)
        assert ">2" in badge.group(1)

    async def test_landing_has_exactly_one_sse_connect(self, example_app) -> None:
        """The headline N→1 win: GET / opens EXACTLY ONE persistent SSE
        connection (the merged /_chirp/live signal stream). The bell no longer
        opens its own /notifications/stream scope — every live topic (ticker,
        balance, notifications, notif_badge, notif_announce) rides the one
        connection."""
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
        assert html.count("sse-connect=") == 1
        assert 'sse-connect="/_chirp/live' in html

    async def test_bell_popover_semantics_are_a_region_not_a_menu(self, example_app) -> None:
        """A11y: the dropdown is a read-only list popover, not a menu. The trigger
        advertises aria-haspopup="dialog" (NOT "menu") and the panel is role="region"
        (NOT role="menu") wrapping a <ul role="list"> — so a screen reader is never
        told 'menu' for a non-navigable list with no menuitems."""
        import re

        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
            # The bell TRIGGER advertises a dialog popover, not a menu (scope to the
            # bell — chirp-ui's shell-actions "More" overflow legitimately ships its
            # own role="menu"/aria-haspopup="menu" dropdown elsewhere in the shell).
            trigger = re.search(r"<button[^>]*luckycat-notif-bell__trigger[^>]*>", html)
            assert trigger is not None, "bell trigger not rendered"
            assert 'aria-haspopup="dialog"' in trigger.group(0)
            assert 'aria-haspopup="menu"' not in trigger.group(0)
            # The bell PANEL is a labelled region (NOT a menu) wrapping a list.
            assert 'role="region" aria-label="Notifications"' in html

    async def test_unread_count_announced_outside_the_button(self, example_app) -> None:
        """A11y: the spoken unread count rides a sibling visually-hidden polite live
        region (#notif-announce) OUTSIDE the labelled bell button — a live region
        nested in a button whose name is fixed by aria-label is suppressed by AT.
        The visual badge inside the button is aria-hidden (decorative there)."""
        import re

        import notifications

        notifications.add("fill", "A")
        notifications.add("fill", "B")
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
            # The sibling live region exists and carries the spoken count.
            assert 'id="notif-announce"' in html
            assert "chirpui-visually-hidden" in html
            assert "2 unread notifications" in html
            # The visual badge wrapper inside the button is no longer a live region.
            badge_wrap = re.search(r'<span id="notif-badge"[^>]*>', html)
            assert badge_wrap is not None
            assert 'aria-live="polite"' not in badge_wrap.group(0)
            assert 'aria-hidden="true"' in badge_wrap.group(0)

    async def test_read_route_clears_count_over_signal(self, example_app) -> None:
        """POST /notifications/read marks the log read and EMITS the `notifications`
        signal so the derived badge + announce recompute to 0 over /_chirp/live.
        The HTTP response is an empty 204 (the trigger posts hx-swap="none"); the
        visible clear flows over the live connection, not a response body."""
        import notifications

        notifications.add("fill", "A")
        assert notifications.unread_count() == 1
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post("/notifications/read", data={}, headers=headers)
            # Empty 204: the signal carries the visible clear, not the body.
            assert response.status == 204
            assert response.text == ""
            # The watermark advanced — the derived badge/announce derive to 0.
            assert notifications.unread_count() == 0

    async def test_bell_persists_across_routes(self, example_app) -> None:
        """The bell lives in the persistent topbar shell, so it ships on every
        route (like the command palette + nav drawer), bound to the one merged
        signal connection on each page (never a per-page /notifications/stream)."""
        async with TestClient(example_app) as client:
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/trade", "/settings"):
                response = await client.get(path)
                assert response.status == 200, path
                assert 'id="notif-bell"' in response.text, path
                assert 'sse-connect="/_chirp/live' in response.text, path
                # The bell's own separate notifications scope is gone everywhere.
                assert 'sse-connect="/notifications/stream"' not in response.text, path

    async def test_shell_pages_have_single_persistent_connection(self, example_app) -> None:
        """The headline N→1 win: shell pages whose ONLY live channel is the chrome
        (ticker + balance + bell) hold EXACTLY ONE persistent SSE connection — the
        merged /_chirp/live. Two pages legitimately open a SECOND, page-specific
        connection and are excluded: /portfolio (the /ft/stream proof panel) and
        the market-detail page (its per-market /markets/{symbol}/stream)."""
        async with TestClient(example_app) as client:
            for path in ("/", "/trade", "/settings", "/watchlist", "/activity"):
                html = (await client.get(path)).text
                assert html.count("sse-connect=") == 1, path
                assert 'sse-connect="/_chirp/live' in html, path
                # The old separate notifications scope is gone everywhere.
                assert 'sse-connect="/notifications/stream"' not in html, path

    async def test_badge_and_rows_render_when_unread(self, example_app) -> None:
        """With notifications on record, the unread pill + the feed rows render in
        the bell dropdown (the single-source notification_row body)."""
        import notifications

        notifications.add("fill", "Filled buy 1 PAW-MEOW", "@ 8 MEOW.")
        notifications.add("deposit", "Deposited 250 $MEOW", "Balance now 1250 $MEOW.")
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            html = response.text
            # Unread pill present with the count, and both rows render.
            assert "luckycat-notif-badge" in html
            assert "Filled buy 1 PAW-MEOW" in html
            assert "Deposited 250 $MEOW" in html
            # Kind-keyed row classes (icon + accent).
            assert "luckycat-notif--fill" in html
            assert "luckycat-notif--deposit" in html

    async def _csrf_headers(self, client, path: str = "/") -> dict:
        page = await client.get(path)
        cookie = extract_session_cookie(page, cookie_name=self._SESSION_COOKIE)
        csrf = extract_csrf_token(page.text)
        assert csrf is not None
        headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}
        if cookie:
            headers["Cookie"] = f"{self._SESSION_COOKIE}={cookie}"
        return headers

    async def test_open_marks_read_clears_watermark(self, example_app) -> None:
        """POST /notifications/read advances the read watermark to zero unread, so
        the derived `notif_badge` / `notif_announce` signals clear over the live
        connection. The response is an empty 204 (no OOB twin body anymore)."""
        import notifications

        notifications.add("fill", "A")
        notifications.add("fill", "B")
        assert notifications.unread_count() == 2
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post("/notifications/read", data={}, headers=headers)
            assert response.status == 204
            assert response.text == ""
            # Server watermark advanced — the derived badge/announce derive to 0.
            assert notifications.unread_count() == 0

    async def test_read_requires_csrf(self, example_app) -> None:
        """The mutating read route is rejected without a CSRF token (secure-by-default)."""
        async with TestClient(example_app) as client:
            response = await client.post("/notifications/read", data={})
            assert response.status in (400, 403)

    async def test_deposit_logs_and_emits_notifications_signal(self, example_app) -> None:
        """A real /deposit credit appends a deposit notification AND emits the
        `notifications` signal, so the bell reacts immediately (the dropdown list
        re-renders + the derived badge/announce recompute) over /_chirp/live. A
        clamped bad amount adds nothing and emits nothing.

        The emit is proved observably via the signal registry's value cache: the
        deposit fans a `NotifFeed` snapshot (rows + unread, atomic) to
        `notifications` and the derived `notif_badge` recomputes PURELY from
        `feed.unread` in the same cascade. ``App.emit`` is read-only
        (frozen/slotted), so we read the cache the cascade populated rather than
        monkeypatching the producer.
        """
        import notifications

        registry = example_app._mutable_state.signal_registry
        assert registry is not None
        # Seed the value cache from the initial() seed (empty), then deposit.
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            await client.post("/deposit", data={"amount": "250"}, headers=headers)
            feed = notifications.recent()
            # The log grew by one deposit entry.
            assert len(feed) == 1
            assert feed[0].kind == "deposit"
            assert "250" in feed[0].title
            # ...AND the deposit emitted the notifications signal: the registry's
            # cache now holds a NotifFeed snapshot (one row, unread=1) and the
            # derived notif_badge recomputed PURELY from feed.unread in the same
            # emit cascade.
            cached = registry.cached_value("notifications")
            assert isinstance(cached, notifications.NotifFeed)
            assert len(cached.notes) == 1
            assert cached.unread == 1
            assert registry.cached_value("notif_badge") == 1
            # A clamped/no-op deposit adds nothing (no new log entry, cache stays 1).
            await client.post("/deposit", data={"amount": "not-a-number"}, headers=headers)
            assert len(notifications.recent()) == 1
            assert len(registry.cached_value("notifications").notes) == 1

    async def test_order_fill_logs_a_notification(self, example_app) -> None:
        """A filled market order appends a fill notification to the bell."""
        import notifications

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client, path="/trade")
            await client.post(
                "/trade/order",
                data={"symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
                headers=headers,
            )
            feed = notifications.recent()
            assert len(feed) == 1
            assert feed[0].kind == "fill"
            assert "PAW-MEOW" in feed[0].title

    async def test_notifications_signal_stream_is_event_stream(self, example_app) -> None:
        """The bell's live channel is now the merged /_chirp/live signal stream
        scoped to the notifications topics (the old separate /notifications/stream
        route is gone). Scoping to ?topics=notifications opens the EventStream."""
        async with TestClient(example_app) as client:
            result = await client.sse(
                "/_chirp/live?topics=notifications,notif_badge,notif_announce",
                max_events=2,
            )
        assert result.status == 200
        assert result.headers.get("content-type") == "text/event-stream"
        # The deleted route 404s — the bell rides /_chirp/live now.
        async with TestClient(example_app) as client:
            gone = await client.sse("/notifications/stream", max_events=1)
        assert gone.status == 404

    async def test_notifications_signal_emits_price_alerts_and_derived_badge(
        self, example_app
    ) -> None:
        """Over enough ticks the `notifications` SOURCE signal raises price-move
        alerts (the moved hysteresis/cooldown walk) and emits `event: notifications`
        carrying the dropdown list body; the derived `notif_badge` re-emits in the
        same cascade as `event: notif_badge`. No OOB row prepends / no raw tags."""
        async with TestClient(example_app) as client:
            result = await client.sse(
                "/_chirp/live?topics=notifications,notif_badge",
                max_events=40,
            )
        notif_events = [e for e in result.events if e.event == "notifications" and e.data]
        assert notif_events, f"no event: notifications frames: {[e.event for e in result.events]}"
        joined = "".join(e.data for e in notif_events)
        # The emitted payload is the dropdown list body (rows), NOT OOB prepends.
        assert "afterbegin:#notif-list" not in joined
        assert "hx-swap-oob" not in joined
        # A price-move alert row was raised by the SimFeed walk (kind-keyed class).
        assert "luckycat-notif--price" in joined
        # The derived badge re-emits in the same cascade (count derived from list).
        badge_events = [e for e in result.events if e.event == "notif_badge"]
        assert badge_events, "derived notif_badge never re-emitted"
        assert "{{" not in joined
        assert "{%" not in joined
