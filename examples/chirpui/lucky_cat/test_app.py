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

import pytest
from store_test_helpers import client_balance, sole_client_store, warm_authed_store

from chirp.testing import TestClient, assert_mutation_redirect
from tests.helpers.auth import (
    csrf_post,
    extract_csrf_token,
    extract_session_cookie,
    login,
)

_SESSION_COOKIE = "chirp_session_lucky_cat"


def _session_cookie(response) -> str | None:
    return extract_session_cookie(response, cookie_name=_SESSION_COOKIE)


async def _login(client) -> str:
    """Sign in as the demo account; return the authenticated session cookie.

    The account surfaces (trade / portfolio / activity / settings) and the
    signed-in topbar chrome (balance token, notifications bell, Deposit modal)
    only render for an authenticated user — and every mutation route is
    ``@login_required`` — so render/mutation tests below sign in first.
    """
    cookie = await login(client, username="neko", password="luckycat", cookie_name=_SESSION_COOKIE)
    assert cookie is not None
    return cookie


def _cookie_header(cookie: str) -> dict:
    """Build a Cookie header for an authed GET of a gated page / signed-in chrome."""
    return {"Cookie": f"{_SESSION_COOKIE}={cookie}"}


class TestContracts:
    """The example should stay clean under startup contract checks."""

    @pytest.mark.issue(229)
    def test_app_check_passes(self, example_app) -> None:
        example_app.check()


class TestHealth:
    """Railway healthcheck."""

    @pytest.mark.issue(221)
    async def test_health_ok(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/health")
            assert response.status == 200
            assert response.text == "ok"


class TestLanding:
    """GET / renders the Lucky Cat shell + the curated Markets Home lobby.

    #281 (PR7) RETIRED the old full markets grid landing for a curated, BOUNDED
    lobby (stat strip + movers/watchlist previews + featured + a Research CTA), and
    made ``/`` an ALIAS rendering the same ``markets/page.html`` as ``/markets``.
    The full catalog moved to Research. These assertions were updated from the old
    grid (``#markets-grid``) to the lobby (``#markets-lobby``); the lobby-specific
    proofs (alias parity, de-dupe footgun, preview-link integrity) live in
    ``test_lobby.py``."""

    async def test_landing_full_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html" in response.text
            # Brand chrome + house token.
            assert "Lucky" in response.text
            assert "$MEOW" in response.text

    @pytest.mark.issue(281)
    async def test_landing_renders_the_lobby(self, example_app) -> None:
        """#281: the landing is the curated lobby (#markets-lobby), NOT the old
        full grid (#markets-grid). The topbar ticker strip is still present."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'id="markets-lobby"' in response.text
            # The retired full-grid landing id is gone.
            assert 'id="markets-grid"' not in response.text
            assert 'id="lucky-cat-ticker"' in response.text

    @pytest.mark.issue(281)
    async def test_landing_renders_live_markets(self, example_app) -> None:
        """#281: the lobby is driven by the live SimFeed — the movers preview shows
        real markets and the featured card carries live price + 24h-change chrome
        (no empty state)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            # The movers preview links real markets (BTC/ETH are warmed markets).
            assert "BTC-MEOW" in response.text
            assert "ETH-MEOW" in response.text
            # The featured card carries live (simulated) price + 24h change chrome.
            assert "luckycat-market-card__price" in response.text
            assert "luckycat-market-card__change" in response.text
            # The empty-catalog state must be gone now that markets are live.
            assert "No markets open yet" not in response.text

    async def test_landing_renders_no_raw_template_tags(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "{%" not in response.text
            assert "{{" not in response.text

    @pytest.mark.issue(297)
    async def test_first_visit_tour_markup_on_public_shell(self, example_app) -> None:
        """#297: the dismissible coachmarks shell ships on first visit (before
        luckycat-tour-seen is set client-side). Public visitors get the SSE step."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'id="luckycat-tour"' in response.text
            assert 'data-tour-seen-key="luckycat-tour-seen"' in response.text
            assert 'data-tour-auth="false"' in response.text
            assert "coachmarks.js" in response.text
            assert "Updated over SSE, zero JS" in response.text

    @pytest.mark.issue(297)
    async def test_first_visit_tour_includes_auth_steps_when_signed_in(self, example_app) -> None:
        """#297: signed-in traders get the full three-step tour seed."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
            assert response.status == 200
            assert 'data-tour-auth="true"' in response.text
            assert "422 re-render in place" in response.text
            assert "Suspense: shell first, panels stream" in response.text

    @pytest.mark.issue(281)
    async def test_landing_has_no_duplicate_element_ids(self, example_app) -> None:
        """No static element id may appear twice in the full-page render. A
        duplicate id is invalid HTML and silently breaks getElementById /
        aria-controls / Alpine $id wiring. For the lobby (#281) this also guards
        the de-dupe footgun: a coin in BOTH the featured slot AND the watchlist
        preview would duplicate ``#luckycat-card-{symbol}`` / ``#watchlist-star-
        {symbol}`` (and break the unstar-prune target). The exhaustive starred-
        featured-coin proof lives in test_lobby.py."""
        import re

        async with TestClient(example_app) as client:
            response = await client.get("/")
        # Static ids only (``id="..."`` preceded by whitespace, so ``grid="`` and
        # Alpine ``:id``/``x-id`` dynamic bindings are not matched).
        ids = re.findall(r'\sid="([^"]+)"', response.text)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        assert not dupes, f"duplicate element ids in GET /: {dupes}"

    @pytest.mark.issue(281)
    async def test_landing_featured_card_renders_gradient_sparkline(self, example_app) -> None:
        """The lobby's featured card carries a server-rendered gradient-area SVG
        sparkline — no JS chart lib, drawn from the candle-close series. The
        featured coin is the catalog's top gainer (computed here so the assertion
        is robust to the deterministic ordering)."""
        import ranking
        import research
        from feed import get_feed

        feed = get_feed()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        rows = research.build_rows(tuple(markets), tickers)
        featured = ranking.market_stats(rows).top_gainer
        assert featured is not None

        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            assert response.status == 200
            # One SVG sparkline + its gradient fill polygon + line polyline.
            assert "luckycat-spark " in html
            assert "luckycat-spark__line" in html
            assert "luckycat-spark__fill" in html
            # Direction is keyed off the series (up=jade / down=red) and the
            # gradient id is namespaced by symbol so multiple cards never collide.
            assert "luckycat-spark--up" in html or "luckycat-spark--down" in html
            # The featured card's namespaced gradient id is present.
            assert f'id="lc-spark-{featured.symbol}-' in html

    async def test_landing_featured_card_marks_direction(self, example_app) -> None:
        """The featured card carries an up/down modifier so the top-edge accent +
        delta pill agree on direction."""
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
            assert "luckycat-market-card--up" in html or "luckycat-market-card--down" in html

    async def test_landing_sparkline_survives_boosted_nav(self, example_app) -> None:
        """The lobby sparkline lives inside page_content, so a boosted (htmx)
        re-render of the lobby keeps the featured card chart — not just the first
        full-page paint."""
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

    @pytest.mark.issue(222)
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

    @pytest.mark.issue(223)
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

    @pytest.mark.issue(230)
    async def test_deposit_action_is_not_inert(self, example_app) -> None:
        """The Deposit button carries data-action="deposit" (the kanban modal
        pattern), NOT an inert href="#". (The Deposit shell action is signed-in
        chrome, so authenticate first.)"""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/", headers=_cookie_header(cookie))
            assert response.status == 200
            assert 'data-action="deposit"' in response.text
            # The old inert placeholder must be gone.
            assert 'href="#"' not in response.text

    async def test_topbar_holds_only_global_actions(self, example_app) -> None:
        """IA doctrine: the topbar holds global actions only — Deposit (primary)
        + About (overflow). Section navigation (Markets) lives in the outer icon
        rail, NOT the topbar, so there is no 'controls' nav zone. (Deposit is the
        signed-in primary action, so authenticate first.)"""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/", headers=_cookie_header(cookie))
            assert response.status == 200
            assert "chirpui-shell-actions__group--primary" in response.text
            # Overflow auto-wraps into a "More" dropdown.
            assert "chirpui-shell-actions__group--overflow" in response.text
            assert "More" in response.text
            # No 'controls' zone: section nav does not belong in the topbar.
            assert "chirpui-shell-actions__group--controls" not in response.text

    async def test_deposit_modal_present(self, example_app) -> None:
        """The deposit dialog + its CSRF-protected form ship inside the page (for
        a signed-in user, who owns the Deposit affordance)."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/", headers=_cookie_header(cookie))
            assert response.status == 200
            assert 'id="deposit-modal"' in response.text
            assert 'id="deposit-form"' in response.text
            # The form is CSRF-protected (hidden field) and posts to /deposit.
            assert 'name="_csrf_token"' in response.text
            assert 'hx-post="/markets"' in response.text

    async def test_balance_renders_in_topbar(self, example_app) -> None:
        """The $MEOW balance is a live `balance` SIGNAL: the topbar token carries
        an sse-swap="balance" sink (signal('balance')) SSR-seeded with the seed
        value. No #lucky-cat-balance OOB id anymore — the signal sink owns it.
        (The $MEOW balance token is signed-in chrome, so authenticate first.)"""
        import wallet

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/", headers=_cookie_header(cookie))
            assert response.status == 200
            # The balance signal binding (the helper emits
            # <span sse-swap="balance" hx-target="this">…</span>).
            assert 'sse-swap="balance"' in response.text
            # ...inside the topbar token chrome.
            token = response.text[response.text.find("luckycat-token__amount") :]
            assert 'sse-swap="balance"' in token
            # SSR seed balance from wallet.INITIAL_MEOW.
            assert str(wallet.INITIAL_MEOW) in response.text
            assert "$MEOW" in response.text

    async def test_deposit_emits_balance_signal(self, example_app) -> None:
        """POST /deposit credits the wallet and EMITS the `balance` signal — the
        visible update fans over /_chirp/live to every signal('balance') binding,
        so the response itself is an empty 204 (the form posts hx-swap="none").
        No hand-maintained OOB twin (the migration's whole point)."""
        import wallet

        wallet.reset()
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            before = wallet.INITIAL_MEOW
            response, _ = await csrf_post(
                client,
                "/markets",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"_action": "deposit", "amount": "250"},
            )
            # Empty 204: the live signal carries the visible update, not the body.
            assert response.status == 204
            assert response.text == ""
            # The wallet was credited (the value the signal emits to every binding).
            assert client_balance() == before + 250

    async def test_deposit_clamps_bad_amount(self, example_app) -> None:
        """A non-numeric/negative amount is a no-op credit — balance never drops.
        The route still returns its empty 204 (the signal emits the unchanged
        value); the clamp is asserted on the wallet, not a rendered body."""
        import wallet

        wallet.reset()
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            before = wallet.INITIAL_MEOW
            response, _ = await csrf_post(
                client,
                "/markets",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"_action": "deposit", "amount": "not-a-number"},
            )
            assert response.status == 204
            # Balance unchanged at the seed value (a clamped no-op credit).
            assert client_balance() == before

    async def test_deposit_requires_csrf(self, example_app) -> None:
        """Without a CSRF token the mutating route is rejected (secure-by-default)."""
        async with TestClient(example_app) as client:
            response = await client.post("/markets", data={"_action": "deposit", "amount": "100"})
            assert response.status in (400, 403)


class TestSessionScopedStores:
    """#285: per-visitor ephemeral wallet state keyed by session cookie."""

    @pytest.mark.issue(285)
    async def test_two_sessions_have_independent_balances(self, example_app) -> None:
        """Two TestClient sessions with different cookies maintain separate $MEOW."""
        import session_store
        import wallet

        wallet.reset()
        async with TestClient(example_app) as client_a, TestClient(example_app) as client_b:
            await client_a.get("/login")
            await client_b.get("/login")
            cookie_a = await _login(client_a)
            cookie_b = await _login(client_b)
            assert cookie_a != cookie_b

            await warm_authed_store(client_a, cookie_a, cookie_name=_SESSION_COOKIE)
            await warm_authed_store(client_b, cookie_b, cookie_name=_SESSION_COOKIE)

            _, cookie_a = await csrf_post(
                client_a,
                "/markets",
                cookie=cookie_a,
                cookie_name=_SESSION_COOKIE,
                data={"_action": "deposit", "amount": "500"},
            )
            keys = session_store.client_keys()
            assert len(keys) == 2
            balances = {
                session_store.balance_for_key(k, balance_seed=wallet.INITIAL_MEOW) for k in keys
            }
            assert wallet.INITIAL_MEOW + 500 in balances
            assert wallet.INITIAL_MEOW in balances

    @pytest.mark.issue(285)
    async def test_two_sessions_have_independent_positions(self, example_app) -> None:
        """A fill in session A must not appear on session B's trade page."""
        async with TestClient(example_app) as client_a, TestClient(example_app) as client_b:
            cookie_a = await _login(client_a)
            cookie_b = await _login(client_b)
            await warm_authed_store(client_a, cookie_a, cookie_name=_SESSION_COOKIE)
            await warm_authed_store(client_b, cookie_b, cookie_name=_SESSION_COOKIE)

            headers_a = await TestTradeOrder()._csrf_headers(client_a)
            response = await client_a.post("/trade", data={"_action": "order", 
                    "symbol": "PAW-MEOW",
                    "side": "buy",
                    "kind": "market",
                    "size": "1",
                },
                headers=headers_a,
            )
            assert response.status == 200
            assert 'id="position-PAW-MEOW"' in response.text

            page_b = await client_b.get("/trade", headers=_cookie_header(cookie_b))
            assert 'id="position-PAW-MEOW"' not in page_b.text
            assert "No open positions" in page_b.text

    @pytest.mark.issue(285)
    async def test_two_sessions_have_independent_notifications(self, example_app) -> None:
        """A deposit in session A must not appear in session B's notification list."""
        async with TestClient(example_app) as client_a, TestClient(example_app) as client_b:
            cookie_a = await _login(client_a)
            cookie_b = await _login(client_b)
            await warm_authed_store(client_a, cookie_a, cookie_name=_SESSION_COOKIE)
            await warm_authed_store(client_b, cookie_b, cookie_name=_SESSION_COOKIE)

            response, _ = await csrf_post(
                client_a,
                "/markets",
                cookie=cookie_a,
                cookie_name=_SESSION_COOKIE,
                data={"_action": "deposit", "amount": "250"},
            )
            assert response.status == 204

            home_a = await client_a.get("/", headers=_cookie_header(cookie_a))
            home_b = await client_b.get("/", headers=_cookie_header(cookie_b))
            assert "Deposited 250 $MEOW" in home_a.text
            assert "Deposited 250 $MEOW" not in home_b.text

    @pytest.mark.issue(315)
    async def test_two_sessions_receive_independent_signal_sse_events(self, example_app) -> None:
        """#315: session-scoped signals fan only to the matching /_chirp/live?aud=…
        connection — a deposit in session A must not surface on session B's SSE."""
        import asyncio

        import session_store

        async def listen_for_deposit(client, cookie: str, key: str, amount: str):
            async def deposit_after_subscribe() -> None:
                await asyncio.sleep(0.05)
                await csrf_post(
                    client,
                    "/markets",
                    cookie=cookie,
                    cookie_name=_SESSION_COOKIE,
                    data={"_action": "deposit", "amount": amount},
                )

            return await asyncio.gather(
                client.sse(
                    f"/_chirp/live?topics=balance&aud={key}",
                    max_events=1,
                    headers=_cookie_header(cookie),
                ),
                deposit_after_subscribe(),
            )

        async with TestClient(example_app) as client_a, TestClient(example_app) as client_b:
            cookie_a = await _login(client_a)
            cookie_b = await _login(client_b)
            await warm_authed_store(client_a, cookie_a, cookie_name=_SESSION_COOKIE)
            keys_a = session_store.client_keys()
            assert len(keys_a) == 1
            key_a = next(iter(keys_a))

            await warm_authed_store(client_b, cookie_b, cookie_name=_SESSION_COOKIE)
            keys_b = session_store.client_keys()
            assert len(keys_b) == 2
            key_b = next(k for k in keys_b if k != key_a)

            result_a, _ = await listen_for_deposit(client_a, cookie_a, key_a, "250")
            result_b, _ = await listen_for_deposit(client_b, cookie_b, key_b, "100")

        joined_a = "".join(e.data for e in result_a.events if e.data)
        joined_b = "".join(e.data for e in result_b.events if e.data)
        # INITIAL_MEOW (100_000) + deposit amount, rendered as str by the balance signal.
        assert "100250" in joined_a
        assert "100250" not in joined_b
        assert "100100" in joined_b
        assert "100100" not in joined_a


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

    @pytest.mark.issue(282)
    async def test_palette_can_reach_favorites(self, example_app) -> None:
        """IA: the ⌘K palette is the "go anywhere" surface, so it must reach
        Favorites (the starred-markets destination, moved from /watchlist →
        /markets/favorites in #282) — not only the rail. The old "watchlist"
        mental-model query still narrows the Go-to group to it (the matcher key
        keeps the legacy term), and so does "favorites"."""
        async with TestClient(example_app) as client:
            for q in ("watchlist", "favorites"):
                response = await client.get("/search", query={"q": q})
                assert response.status == 200, q
                # The destination now points at the moved page.
                assert 'href="/markets/favorites"' in response.text, q
                assert 'href="/watchlist"' not in response.text, q
                assert "Starred markets" in response.text, q
                # Markets (no matching substring) are filtered out.
                assert "BTC-MEOW" not in response.text, q


class TestActivityFeed:
    """The Activity landing is a real MERGED feed (deposits + fills interleaved
    by ts, newest first), not the old static 'No activity yet' stub."""

    async def test_landing_is_merged_feed_not_static_stub(self, example_app) -> None:
        """With a deposit and a fill on record, the landing renders BOTH rows in
        the shared fills table — never the old stub copy that asserted no data."""

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            headers = {"Cookie": f"{_SESSION_COOKIE}={cookie}", "HX-Request": "true"}
            page = await client.get("/", headers=headers)
            csrf = extract_csrf_token(page.text)
            cookie = extract_session_cookie(page, cookie_name=_SESSION_COOKIE) or cookie
            headers = {
                "X-CSRF-Token": csrf,
                "HX-Request": "true",
                "Cookie": f"{_SESSION_COOKIE}={cookie}",
            }
            await client.post("/markets", data={"_action": "deposit", "amount": "250"}, headers=headers)
            await client.post("/trade", data={"_action": "order", "symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
                headers=headers,
            )
            response = await client.get("/activity", headers=_cookie_header(cookie))
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
            cookie = await _login(client)
            response = await client.get("/activity", headers=_cookie_header(cookie))
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
        order = trade_store.place_order_or_raise("PAW-MEOW", "buy", "market", size)
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

        trade_store.place_order_or_raise("PAW-MEOW", "buy", "market", 2.0)
        mid = wallet.balance()
        trade_store.place_order_or_raise("PAW-MEOW", "sell", "market", 2.0)
        # Position fully closed (cleared), wallet credited above the mid.
        assert trade_store.position("PAW-MEOW") is None
        assert wallet.balance() >= mid

    def test_validate_insufficient_balance(self) -> None:
        import trade_store

        # A huge BTC buy can't be covered by the seed wallet.
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
        trade_store.place_order_or_raise("PAW-MEOW", "buy", "market", 1.0)
        # After a buy, value is cash + mark-to-market (>= remaining cash).
        assert trade_store.portfolio_value() >= wallet.balance()

    @pytest.mark.issue(296)
    def test_market_buy_eats_ask_depth_and_prints_tape(self) -> None:
        """#296: a market buy consumes top-of-book asks and appends to the tape."""
        import trade_store
        from feed import get_feed

        feed = get_feed()
        symbol = "PAW-MEOW"
        book_before = feed.order_book(symbol, depth=3)
        tape_before = feed.trades(symbol, limit=30)
        top_ask_before = book_before.asks[0]
        size = 1.0

        trade_store.place_order_or_raise(symbol, "buy", "market", size)

        book_after = feed.order_book(symbol, depth=3)
        tape_after = feed.trades(symbol, limit=30)
        assert book_after.asks[0].price == top_ask_before.price
        assert book_after.asks[0].size == pytest.approx(top_ask_before.size - size, abs=1e-6)
        assert tape_after[0].side == "buy"
        assert tape_after[0].size == size
        assert tape_after[0].id > tape_before[0].id


class TestTradePage:
    """#225: GET /trade renders the place-order form + positions + count."""

    async def test_trade_page_renders_form(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/trade", headers=_cookie_header(cookie))
            assert response.status == 200
            assert 'id="order-form"' in response.text
            # CSRF protected (hidden field) and posts to the trade route.
            assert 'name="_csrf_token"' in response.text
            assert 'hx-post="/trade"' in response.text
            # OOB targets exist in the rendered DOM (fail-loud).
            assert 'id="positions"' in response.text
            assert 'id="open-order-count"' in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text


class TestTradeOrder:
    """#225: POST /trade/order — validation + multi-target OOB fill."""

    async def _csrf_headers(self, client, *, htmx: bool = True) -> dict:
        """Authed CSRF headers for the gated trade routes.

        ``/trade`` is ``@login_required`` and every order route is a gated
        mutation, so this signs in first, then pairs a CSRF token + session
        cookie from an authed GET of ``/trade``. The returned header set carries
        the matched (token, cookie) pair and is reusable for concurrent requests
        within the session (the CSRF token is per-session, not per-request-nonce).
        """
        cookie = await _login(client)
        page = await client.get("/trade", headers=_cookie_header(cookie))
        cookie = _session_cookie(page) or cookie
        csrf = extract_csrf_token(page.text)
        assert csrf is not None
        headers = {"X-CSRF-Token": csrf}
        if htmx:
            headers["HX-Request"] = "true"
        headers["Cookie"] = f"{_SESSION_COOKIE}={cookie}"
        return headers

    @pytest.mark.issue(225)
    async def test_invalid_order_returns_422_with_field_error(self, example_app) -> None:
        """Insufficient balance -> 422 + re-rendered form with the field error,
        no full-page nav (the order_form block, not the whole page)."""
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post("/trade", data={"_action": "order", "symbol": "BTC-MEOW", "side": "buy", "kind": "market", "size": "10"},
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
            before = wallet.INITIAL_MEOW
            response = await client.post("/trade", data={"_action": "order", "symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
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
            assert client_balance() < before

    @pytest.mark.issue(296)
    async def test_market_buy_via_http_eats_book_and_prints_tape(self, example_app) -> None:
        """POST /trade/order market fill updates SimFeed book depth + trade tape."""
        from feed import get_feed

        feed = get_feed()
        symbol = "PAW-MEOW"
        book_before = feed.order_book(symbol, depth=3)
        tape_before = feed.trades(symbol, limit=30)
        top_ask_before = book_before.asks[0]
        size = 1.0

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post("/trade", data={"_action": "order", 
                    "symbol": symbol,
                    "side": "buy",
                    "kind": "market",
                    "size": str(size),
                },
                headers=headers,
            )
            assert response.status == 200

        book_after = feed.order_book(symbol, depth=3)
        tape_after = feed.trades(symbol, limit=30)
        assert book_after.asks[0].price == top_ask_before.price
        assert book_after.asks[0].size == pytest.approx(top_ask_before.size - size, abs=1e-6)
        assert tape_after[0].side == "buy"
        assert tape_after[0].size == size
        assert tape_after[0].id > tape_before[0].id

    async def test_order_requires_csrf(self, example_app) -> None:
        """Without a CSRF token the mutating route is rejected (secure-by-default)."""
        async with TestClient(example_app) as client:
            response = await client.post("/trade", data={"_action": "order", "symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
            )
            assert response.status in (400, 403)

    async def test_plain_post_redirects(self, example_app) -> None:
        """A plain (non-htmx) POST gets the FormAction 303 redirect to /trade."""
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client, htmx=False)
            response = await client.post("/trade", data={"_action": "order", "symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
                headers=headers,
            )
            assert_mutation_redirect(response, "/trade")

    async def test_cancel_order_updates_count_and_toast(self, example_app) -> None:
        """Cancelling a resting order OOB-swaps the open-order count + a toast."""
        import trade_store

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            with sole_client_store():
                order = trade_store.open_limit_order("SOL-MEOW", "buy", 1.0, 100.0)
            response = await client.post(
                "/portfolio/orders",
                data={"_action": "cancel", "order_id": str(order.id)},
                headers=headers,
            )
            assert response.status == 200
            assert 'id="open-order-count"' in response.text
            assert "cancelled" in response.text.lower()
            with sole_client_store():
                assert trade_store.open_order_count() == 0

    async def test_cancel_last_order_oob_swaps_empty_state(self, example_app) -> None:
        """Cancelling the LAST resting order ALSO OOB-swaps the #open-orders-table
        container to the empty-state — so the orders page never shows a bare
        thead (the row deletes itself, but the empty state must appear without a
        reload). Fail-loud: the swap targets a real id that the orders page ships."""
        import trade_store

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            await client.post("/trade", data={"_action": "order", 
                    "symbol": "SOL-MEOW",
                    "side": "buy",
                    "kind": "limit",
                    "size": "1",
                    "limit_price": "100",
                },
                headers=headers,
            )
            with sole_client_store():
                order = trade_store.open_orders()[0]
            orders_page = await client.get("/portfolio/orders", headers=headers)
            assert 'id="open-orders-table"' in orders_page.text

            headers = await self._csrf_headers(client)
            response = await client.post(
                "/portfolio/orders", data={"_action": "cancel", "order_id": str(order.id)}, headers=headers
            )
            assert response.status == 200
            # The empty-table OOB swap fired, targeting the real container id.
            assert 'id="open-orders-table"' in response.text
            assert "hx-swap-oob" in response.text
            # It carries the empty-state, not a bare table.
            assert "No resting orders" in response.text
            with sole_client_store():
                assert trade_store.open_order_count() == 0
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_cancel_non_last_order_no_table_swap(self, example_app) -> None:
        """Cancelling a NON-last order leaves the #open-orders-table untouched
        (the per-row delete handles it) — no wasteful full-table OOB swap; only
        the count badge + toast update."""
        import trade_store

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            with sole_client_store():
                first = trade_store.open_limit_order("SOL-MEOW", "buy", 1.0, 100.0)
                trade_store.open_limit_order("BTC-MEOW", "sell", 0.5, 90000.0)
            response = await client.post(
                "/portfolio/orders", data={"_action": "cancel", "order_id": str(first.id)}, headers=headers
            )
            assert response.status == 200
            # Count badge still updates, but the table container does NOT swap.
            assert 'id="open-order-count"' in response.text
            assert 'id="open-orders-table"' not in response.text
            with sole_client_store():
                assert trade_store.open_order_count() == 1

    async def test_limit_order_rests_and_bumps_count(self, example_app) -> None:
        """#225 + LOW-1: a LIMIT order rests (no fill, no debit) and bumps the live
        open-order count — wiring the previously-dead resting-limit path through
        the route. A market order fills; a limit order joins the book."""
        import trade_store
        import wallet

        before = wallet.INITIAL_MEOW
        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            response = await client.post("/trade", data={"_action": "order", 
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
        with sole_client_store():
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
                # Size 9000 PAW-MEOW ≈ 73k $MEOW each: every buy validates against the
                # 100k seed alone, but two cannot both clear — the loser hits the
                # atomic re-check and gets a 422, not a 500.
                resp = await client.post("/trade", data={"_action": "order", 
                        "symbol": "PAW-MEOW",
                        "side": "buy",
                        "kind": "market",
                        "size": "9000",
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
        with sole_client_store():
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
        # Each buy costs ~73k $MEOW; only one of these can clear against 100k.
        price = get_feed().ticker("PAW-MEOW").price
        size = 9000.0
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

    def test_no_route_uses_raising_fill(self) -> None:
        """#292: the raising ``place_order_or_raise`` must never be the HTTP fill
        path — every trade action goes through the atomic ``try_place_order``."""
        import pathlib

        root = pathlib.Path(__file__).parent
        trade_sources = (
            root / "pages" / "trade" / "_actions.py",
            root / "pages" / "trade" / "convert" / "_actions.py",
        )
        combined = "\n".join(p.read_text(encoding="utf-8") for p in trade_sources)
        assert "place_order_or_raise" not in combined
        assert "try_place_order" in combined


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

    @pytest.mark.issue(282)
    def test_reserved_segments_are_not_coins(self) -> None:
        """CRITICAL footgun guard: the fixed Markets destinations live one level
        under /markets just like a coin, but must NOT be pinned as a coin-detail
        route (they'd light a phantom 'Viewing' lane and read current_symbol as a
        view name). The RESERVED_MARKET_SEGMENTS guard runs before the depth
        check."""
        from navigation import RESERVED_MARKET_SEGMENTS, route_state

        assert frozenset({"favorites", "trending", "research"}) == RESERVED_MARKET_SEGMENTS
        for seg in ("favorites", "trending", "research"):
            s = route_state(f"/markets/{seg}")
            assert s.market_detail_active is False, seg
            assert s.current_symbol == "", seg
            # All still belong to the Markets room.
            assert s.active_room == "markets", seg
        # Favorites has its own active flag (drives the rail's Favorites lane).
        assert route_state("/markets/favorites").favorites_active is True
        assert route_state("/markets/BTC-MEOW").favorites_active is False
        # A genuine coin (not reserved) still reads as a detail route.
        assert route_state("/markets/BTC-MEOW").market_detail_active is True

    @pytest.mark.issue(282)
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
        # Markets room: the FIXED destinations (Home / Favorites / Trending /
        # Research), NOT an O(N) one-row-per-market list. Exactly four lanes,
        # independent of the catalog size.
        market_section = next(s for s in nav.sidebar_sections if s.key == "markets")
        assert tuple(i.key for i in market_section.items) == (
            "nav:home",
            "nav:favorites",
            "nav:trending",
            "nav:research",
        )
        assert tuple(i.href for i in market_section.items) == (
            "/",
            "/markets/favorites",
            "/markets/trending",
            "/markets/research",
        )
        # On /, Home is the active destination.
        home = next(i for i in market_section.items if i.key == "nav:home")
        assert home.active is True

        # Portfolio room dispatches to its own sections (no markets list).
        pnav = shell_navigation(route_state("/portfolio"), markets=markets, tickers=tickers)
        assert {s.key for s in pnav.sidebar_sections} == {"portfolio"}
        # No empty sections survive pruning.
        assert all(s.items for s in pnav.sidebar_sections)

    @pytest.mark.issue(282)
    def test_coin_detail_pins_current_coin_without_dead_anchors(self) -> None:
        """A coin-detail route PINS the current coin at the top of the rail (a
        single active lane with its 24h badge), then the fixed destinations below.
        The dead #order-book / #trade-tape / #info jump anchors are GONE."""
        from feed import SimFeed
        from navigation import route_state, shell_navigation

        feed = SimFeed(seed=1)
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}

        nav = shell_navigation(route_state("/markets/BTC-MEOW"), markets=markets, tickers=tickers)
        pinned = next(s for s in nav.sidebar_sections if s.key == "this-market")
        # Exactly the one pinned coin lane (no Overview/Book/Trades/Info anchors).
        assert len(pinned.items) == 1
        coin = pinned.items[0]
        assert coin.key == "mkt:BTC-MEOW"
        assert coin.href == "/markets/BTC-MEOW"
        assert coin.active is True
        # No section emits a dead #fragment jump anchor.
        for section in nav.sidebar_sections:
            for item in section.items:
                assert "#" not in item.href, item.href
        # The fixed destinations still render below the pinned coin.
        market_section = next(s for s in nav.sidebar_sections if s.key == "markets")
        assert tuple(i.key for i in market_section.items) == (
            "nav:home",
            "nav:favorites",
            "nav:trending",
            "nav:research",
        )


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
        """The five rooms appear on every route (markets / detail / a new room).

        Some routes are gated (/portfolio, /settings), so sign in once and carry
        the authed cookie across the loop."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/settings"):
                response = await client.get(path, headers=_cookie_header(cookie))
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
            cookie = await _login(client)
            home = await client.get("/", headers=_cookie_header(cookie))
            # On /, exactly the Markets room (href="/") is active.
            assert self._active_room_hrefs(home.text) == {"/"}

            pf = await client.get("/portfolio", headers=_cookie_header(cookie))
            # Active marker moves to Portfolio, and only Portfolio.
            assert self._active_room_hrefs(pf.text) == {"/portfolio"}

            st = await client.get("/settings", headers=_cookie_header(cookie))
            # The Settings room lights up, and only Settings.
            assert self._active_room_hrefs(st.text) == {"/settings"}

            detail = await client.get("/markets/BTC-MEOW", headers=_cookie_header(cookie))
            # A market-detail route stays in the Markets room (path-prefix).
            assert self._active_room_hrefs(detail.text) == {"/"}

    @pytest.mark.issue(282)
    async def test_inner_rail_changes_by_route(self, example_app) -> None:
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            markets = await client.get("/", headers=_cookie_header(cookie))
            # Markets room → the FIXED destinations (Home / Favorites / Trending /
            # Research). No O(N) market list, no cosmetic Filters header, no dead
            # "All markets" lane.
            for label in ("Home", "Favorites", "Trending", "Research"):
                assert f">{label}</span>" in markets.text, label
            assert 'href="/markets/favorites"' in markets.text
            assert 'href="/markets/trending"' in markets.text
            assert 'href="/markets/research"' in markets.text
            assert "All markets" not in markets.text
            assert ">Filters</" not in markets.text

            detail = await client.get("/markets/BTC-MEOW", headers=_cookie_header(cookie))
            # Coin-detail route → the pinned coin at the top, then the same fixed
            # destinations. The dead Overview/Order-book/Trades/Info rail anchors
            # are GONE (the rail no longer emits #order-book/#trade-tape/#info hrefs).
            assert 'href="/markets/favorites"' in detail.text
            assert 'href="/markets/trending"' in detail.text
            # No dead jump-anchor hrefs in the rail/drawer nav.
            assert 'href="/markets/BTC-MEOW#order-book"' not in detail.text
            assert 'href="/markets/BTC-MEOW#trade-tape"' not in detail.text
            assert 'href="/markets/BTC-MEOW#info"' not in detail.text

            portfolio = await client.get("/portfolio", headers=_cookie_header(cookie))
            # Portfolio room → holdings / open orders / history; no Markets lanes.
            assert "Holdings" in portfolio.text
            assert "Open orders" in portfolio.text
            assert 'href="/markets/trending"' not in portfolio.text

    @pytest.mark.issue(282)
    async def test_pinned_coin_carries_change_badge(self, example_app) -> None:
        """The rail no longer lists every market (the fixed destinations replaced
        the O(N) list), so the signed 24h-change pill now rides the PINNED coin on
        a coin-detail route rather than every landing-rail row."""
        async with TestClient(example_app) as client:
            # Landing: the fixed destinations carry no per-market change badge.
            landing = await client.get("/")
            assert "luckycat-inner-rail__badge" not in landing.text
            # Coin-detail: the pinned coin lane carries its signed 24h pill.
            detail = await client.get("/markets/BTC-MEOW")
            assert "luckycat-inner-rail__badge" in detail.text
            assert "%" in detail.text

    @staticmethod
    def _brand_link_tag(html: str) -> str:
        import re

        m = re.search(r'<a [^>]*class="chirpui-app-shell__brand"[^>]*>', html)
        assert m is not None, "brand/logo link not found"
        return m.group(0)

    @pytest.mark.issue(298)
    async def test_brand_logo_carries_boosted_outlet_select(self, example_app) -> None:
        """Regression (#298): the brand/logo is a full boosted shell-outlet link.

        Clicking the logo from a coin-detail route used to duplicate the whole
        shell inside ``#main`` because chirp-ui's ``shell_brand_link`` builds its
        anchor via ``route_link_attrs``, whose resolver emits only
        ``hx-target`` + ``hx-boost`` (NO ``hx-select``). A boosted request returns
        the full shell document, so an ``innerHTML`` swap into ``#main`` without a
        select nests the shell. The brand link MUST carry the same outlet contract
        every other boosted nav element uses (``shell_outlet_attrs()``)."""
        async with TestClient(example_app) as client:
            # The bug manifested specifically from a coin-detail route.
            detail = await client.get("/markets/SOL-MEOW")
            assert detail.status == 200
            brand = self._brand_link_tag(detail.text)
            assert 'hx-target="#main"' in brand
            assert 'hx-swap="innerHTML"' in brand
            assert 'hx-select="#page-content"' in brand, (
                "brand/logo missing hx-select -> boosted swap nests the shell (#298)"
            )
            # Same on the landing itself.
            home = await client.get("/")
            assert 'hx-select="#page-content"' in self._brand_link_tag(home.text)

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
            cookie = await _login(client)
            response = await client.get(
                "/portfolio",
                headers={
                    "HX-Request": "true",
                    "HX-Boosted": "true",
                    "HX-Target": "main",
                    **_cookie_header(cookie),
                },
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
            cookie = await _login(client)
            for path, heading in (
                ("/portfolio", "Portfolio"),
                ("/trade", "Trade"),
                ("/activity", "Activity"),
                ("/settings", "Settings"),
            ):
                response = await client.get(path, headers=_cookie_header(cookie))
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
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
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

    @pytest.mark.issue(282)
    async def test_nav_drawer_shows_favorites_count(self, example_app) -> None:
        """The mobile drawer's Favorites lane shows its starred-count badge — the
        layout threads watchlist_count through mobile_drawer_nav so the drawer
        does not silently drop the count the desktop rail shows. (Moved from
        /watchlist → /markets/favorites in #282.)"""
        import re

        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                watchlist.add("BTC-MEOW")
                watchlist.add("SOL-MEOW")
            response = await client.get("/", headers=_cookie_header(cookie))
            assert response.status == 200
            match = re.search(r"luckycat-nav-drawer__nav.*?</nav>", response.text, re.S)
            assert match is not None
            drawer = match.group(0)
            # The Favorites lane is present with its count badge (2 starred).
            assert "/markets/favorites" in drawer
            # The old /watchlist href is gone from the drawer.
            assert 'href="/watchlist"' not in drawer
            # The drawer renders item.count via the chirp-ui sidebar badge.
            wl = drawer[drawer.find("/markets/favorites") :]
            badge = re.search(r'class="chirpui-sidebar__badge[^"]*">\s*2\s*<', wl)
            assert badge is not None, "drawer favorites count badge missing"

    async def test_nav_drawer_does_not_duplicate_rail_oob_id(self, example_app) -> None:
        """#chirpui-sidebar-nav is the inline rail's OOB target — it must appear
        exactly once. A duplicate (e.g. if the drawer reused the rail wholesale)
        would break the boosted-nav OOB swap."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/settings"):
                response = await client.get(path, headers=_cookie_header(cookie))
                assert response.status == 200, path
                assert response.text.count('id="chirpui-sidebar-nav"') == 1, path
                assert response.text.count('id="lucky-cat-nav"') == 1, path

    async def test_nav_drawer_persists_across_routes(self, example_app) -> None:
        """The drawer ships on every route (it lives in the persistent topbar
        shell), so the hamburger works no matter where boosted nav landed."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/trade", "/settings"):
                response = await client.get(path, headers=_cookie_header(cookie))
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
    """#231: the cookie-persisted, server-side-first rail COLLAPSE.

    The inner contextual rail collapses to the bare icon rail via a discoverable
    toggle button (``data-luckycat-rail-toggle``) — a click-toggle, NOT a
    continuous drag-resizer (a first-class resizable rail belongs in the chirp-ui
    peer package; see #231's locked decision). The collapse preference rides a
    namespaced cookie (``luckycat_rail_collapsed``) read server-side so the first
    paint is already collapsed (no FOUC): the layout pre-renders a cookie-gated
    ``<style>`` the shell JS then disables.
    """

    _COOKIE = "luckycat_rail_collapsed"

    async def test_collapse_toggle_renders_in_rail(self, example_app) -> None:
        """The collapse toggle ships INSIDE the rail (so it survives OOB swaps)
        and the shell script is wired. There is NO drag-resize handle (reverted
        per #231's locked cookie-collapse decision)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "data-luckycat-rail-toggle" in response.text
            assert 'src="/static/lucky-cat-shell.js"' in response.text
            # The reverted drag-resizer is gone.
            assert "luckycat-sidebar-resize" not in response.text
            assert "data-luckycat-rail-resize" not in response.text

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
            cookie = await _login(client)
            response = await client.get(
                "/portfolio",
                headers={
                    "HX-Request": "true",
                    "HX-Boosted": "true",
                    "HX-Target": "main",
                    **_cookie_header(cookie),
                },
            )
            assert response.status == 200
            oob = response.text[response.text.find('id="chirpui-sidebar-nav"') :]
            assert "data-luckycat-rail-toggle" in oob

    async def test_default_is_expanded_no_precollapse_style(self, example_app) -> None:
        """With no cookie the rail renders expanded — the pre-collapse <style>
        gate is absent and the toggle reports aria-expanded="true"."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert 'id="luckycat-rail-cookie-state"' not in response.text
            assert 'aria-expanded="true"' in response.text

    @pytest.mark.issue(231)
    async def test_collapsed_cookie_pre_renders_collapsed_state(self, example_app) -> None:
        """The headline no-FOUC guarantee (#231's locked decision): a collapsed
        cookie makes the SERVER emit the pre-collapse <style> on first paint, so
        the rail is already collapsed before any JS runs."""
        async with TestClient(example_app) as client:
            response = await client.get("/", headers={"Cookie": f"{self._COOKIE}=true"})
            assert response.status == 200
            # Server-rendered pre-collapse <style> (keyed on the cookie, no FOUC).
            assert 'id="luckycat-rail-cookie-state"' in response.text
            # It collapses the shell sidebar column to the icon-rail width.
            assert "--chirpui-sidebar-width: var(--luckycat-icon-rail-width" in response.text

    async def test_expanded_cookie_renders_expanded(self, example_app) -> None:
        """An explicit ``false`` cookie is treated as expanded (round-trip)."""
        async with TestClient(example_app) as client:
            response = await client.get("/", headers={"Cookie": f"{self._COOKIE}=false"})
            assert response.status == 200
            assert 'id="luckycat-rail-cookie-state"' not in response.text

    async def test_collapse_state_survives_boosted_oob_swap(self, example_app) -> None:
        """A collapsed rail stays usable across boosted navigation: the toggle
        re-ships in the sidebar OOB chunk so the user can always re-expand."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get(
                "/portfolio",
                headers={
                    "HX-Request": "true",
                    "HX-Boosted": "true",
                    "HX-Target": "main",
                    # The rail-collapse cookie + the auth session cookie ride the
                    # one Cookie header together (gated page, collapsed rail).
                    "Cookie": f"{self._COOKIE}=true; {_SESSION_COOKIE}={cookie}",
                },
            )
            assert response.status == 200
            oob = response.text[response.text.find('id="chirpui-sidebar-nav"') :]
            assert "data-luckycat-rail-toggle" in oob

    def test_rail_is_collapsed_reads_cookie(self) -> None:
        """The server reader is pure: no request in scope → expanded default."""
        from shell import RAIL_COLLAPSED_COOKIE, rail_is_collapsed

        assert RAIL_COLLAPSED_COOKIE == "luckycat_rail_collapsed"
        # No request in the ContextVar → safe default (expanded).
        assert rail_is_collapsed() is False


class TestPortfolioDashboard:
    """#224: GET /portfolio is a Suspense dashboard — shell paints instantly with
    skeletons, then six deferred panels stream in as OOB swaps."""

    async def test_shell_renders_all_panel_targets(self, example_app) -> None:
        """The shell ships every deferred panel's DOM id (the OOB swap targets
        must exist — fail-loud) plus skeleton placeholders."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
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
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
            assert response.status == 200
            # Deferred blocks have streamed in: the empty holdings state shows.
            assert "No holdings yet" in response.text
            # And the all-cash allocation empty branch resolved too.
            assert "All cash" in response.text

    async def test_value_reflects_seed_wallet(self, example_app) -> None:
        """With no positions, portfolio value == the seed $MEOW wallet balance."""
        import wallet

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
            assert response.status == 200
            # Seed wallet (INITIAL_MEOW), zero P&L, all cash.
            assert str(wallet.INITIAL_MEOW) in response.text
            assert "$MEOW" in response.text
            assert "unrealized" in response.text.lower()

    async def test_holdings_render_after_a_fill(self, example_app) -> None:
        """A booked position shows up in the deferred holdings table (loaded
        branch), proving the empty-vs-loaded distinction works both ways."""
        import trade_store

        trade_store.place_order_or_raise("PAW-MEOW", "buy", "market", 1.0)
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
            assert response.status == 200
            # The position taped into the holdings table (not the empty state).
            assert "PAW-MEOW" in response.text
            assert "No holdings yet" not in response.text

    @pytest.mark.issue(224)
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
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
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
            cookie = await _login(client)
            response = await client.get(
                "/portfolio",
                headers={"HX-Request": "true", **_cookie_header(cookie)},
            )
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
            cookie = await _login(client)
            response = await client.get("/portfolio", headers=_cookie_header(cookie))
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
        single /_chirp/live signal connection ship on the landing page (the bell
        is signed-in chrome, so authenticate first)."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/", headers=_cookie_header(cookie))
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

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                notifications.add("fill", "Filled buy 1 PAW-MEOW", "@ 8 MEOW.")
                notifications.add("deposit", "Deposited 250 $MEOW", "Balance now 1250 $MEOW.")
            html = (await client.get("/", headers=_cookie_header(cookie))).text
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
            cookie = await _login(client)
            html = (await client.get("/", headers=_cookie_header(cookie))).text
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

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                notifications.add("fill", "A")
                notifications.add("fill", "B")
            html = (await client.get("/", headers=_cookie_header(cookie))).text
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

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            with sole_client_store():
                notifications.add("fill", "A")
                assert notifications.unread_count() == 1
            response = await client.post("/notifications/read", data={}, headers=headers)
            assert response.status == 204
            assert response.text == ""
            with sole_client_store():
                assert notifications.unread_count() == 0

    async def test_bell_persists_across_routes(self, example_app) -> None:
        """The bell lives in the persistent topbar shell, so it ships on every
        route (like the command palette + nav drawer), bound to the one merged
        signal connection on each page (never a per-page /notifications/stream)."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            for path in ("/", "/markets/BTC-MEOW", "/portfolio", "/trade", "/settings"):
                response = await client.get(path, headers=_cookie_header(cookie))
                # The session cookie rotates per response — thread the latest so
                # the next gated GET in the loop stays authenticated.
                cookie = _session_cookie(response) or cookie
                assert response.status == 200, path
                # NOTE: /portfolio currently fails this assertion — see the
                # source-side gap surfaced in the implementer report (the Suspense
                # shell renders after AuthMiddleware's request-user ContextVar is
                # reset, so current_user() reads anonymous and the signed-in bell
                # chrome is dropped; the page already documents this exact issue
                # for csrf_token() and captures it, but not the user). Kept intact
                # (no assertion weakening, no source edit) per the task scope.
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
            cookie = await _login(client)
            for path in ("/", "/trade", "/settings", "/markets/favorites", "/activity"):
                html = (await client.get(path, headers=_cookie_header(cookie))).text
                assert html.count("sse-connect=") == 1, path
                assert 'sse-connect="/_chirp/live' in html, path
                # The old separate notifications scope is gone everywhere.
                assert 'sse-connect="/notifications/stream"' not in html, path

    async def test_badge_and_rows_render_when_unread(self, example_app) -> None:
        """With notifications on record, the unread pill + the feed rows render in
        the bell dropdown (the single-source notification_row body)."""
        import notifications

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                notifications.add("fill", "Filled buy 1 PAW-MEOW", "@ 8 MEOW.")
                notifications.add("deposit", "Deposited 250 $MEOW", "Balance now 1250 $MEOW.")
            response = await client.get("/", headers=_cookie_header(cookie))
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
        """Authed CSRF headers for the bell's gated mutation routes.

        The bell + its mutation routes (/notifications/read, /deposit,
        /trade/order) require a signed-in user, so sign in first, then pair a
        CSRF token + session cookie from an authed GET of ``path``."""
        cookie = await _login(client)
        page = await client.get(path, headers=_cookie_header(cookie))
        cookie = extract_session_cookie(page, cookie_name=self._SESSION_COOKIE) or cookie
        csrf = extract_csrf_token(page.text)
        assert csrf is not None
        headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}
        headers["Cookie"] = f"{self._SESSION_COOKIE}={cookie}"
        return headers

    async def test_open_marks_read_clears_watermark(self, example_app) -> None:
        """POST /notifications/read advances the read watermark to zero unread, so
        the derived `notif_badge` / `notif_announce` signals clear over the live
        connection. The response is an empty 204 (no OOB twin body anymore)."""
        import notifications

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client)
            with sole_client_store():
                notifications.add("fill", "A")
                notifications.add("fill", "B")
                assert notifications.unread_count() == 2
            response = await client.post("/notifications/read", data={}, headers=headers)
            assert response.status == 204
            assert response.text == ""
            with sole_client_store():
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
            await client.post("/markets", data={"_action": "deposit", "amount": "250"}, headers=headers)
            with sole_client_store():
                feed = notifications.recent()
                assert len(feed) == 1
                assert feed[0].kind == "deposit"
                assert "250" in feed[0].title
            # ...AND the deposit emitted the notifications signal: the registry's
            # cache now holds a NotifFeed snapshot (one row, unread=1) and the
            # derived notif_badge recomputed PURELY from feed.unread in the same
            # emit cascade.
            import session_store

            aud = session_store.latest_client_key()
            cached = registry.cached_value("notifications", audience_key=aud)
            assert isinstance(cached, notifications.NotifFeed)
            assert len(cached.notes) == 1
            assert cached.unread == 1
            assert registry.cached_value("notif_badge", audience_key=aud) == 1
            # A clamped/no-op deposit adds nothing (no new log entry, cache stays 1).
            await client.post("/markets", data={"_action": "deposit", "amount": "not-a-number"}, headers=headers)
            with sole_client_store():
                assert len(notifications.recent()) == 1
            assert len(registry.cached_value("notifications", audience_key=aud).notes) == 1

    async def test_order_fill_logs_a_notification(self, example_app) -> None:
        """A filled market order appends a fill notification to the bell."""
        import notifications

        async with TestClient(example_app) as client:
            headers = await self._csrf_headers(client, path="/trade")
            await client.post("/trade", data={"_action": "order", "symbol": "PAW-MEOW", "side": "buy", "kind": "market", "size": "1"},
                headers=headers,
            )
            with sole_client_store():
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
        """Over enough ticks the price-alert loop fans out scoped ``notifications``
        events (dropdown list body) and derived ``notif_badge`` in the same cascade."""
        import session_store

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            aud = session_store.latest_client_key()
            result = await client.sse(
                f"/_chirp/live?topics=notifications,notif_badge&aud={aud}",
                max_events=40,
                headers=_cookie_header(cookie),
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

    @pytest.mark.issue(356)
    async def test_fan_out_notifications_skips_keyless_buckets(self, example_app) -> None:
        """fan_out_notifications_live must never emit the session-scoped
        ``notifications`` signal with an empty audience_key. The DEFAULT_KEY /
        anonymous bucket has no live audience and the framework rejects empty-key
        emits on session signals (a ValueError that previously propagated out of
        the source and killed the pump — a permanently dead bell). It must be
        skipped, not coerced to ``""``."""
        from wiring.app_factory import fan_out_notifications_live
        import notifications
        import session_store

        # A store holding ONLY the DEFAULT_KEY bucket (anonymous / pre-store-key
        # state): the old code coerced this to audience_key="" and raised.
        with session_store.bind(session_store.DEFAULT_KEY):
            notifications.add("system", "seed", "")
        assert session_store.DEFAULT_KEY in session_store.store_keys()
        assert not session_store.client_keys()

        # Must be a no-op, NOT a ValueError.
        fan_out_notifications_live()

    @pytest.mark.issue(356)
    async def test_fan_out_notifications_emits_to_real_session(self, example_app) -> None:
        """A real (non-default) session key fans out without the empty-key error
        and caches that session's notifications snapshot."""
        from wiring.app_factory import fan_out_notifications_live
        import app as lucky_app
        import notifications
        import session_store

        key = "sess-regression"
        with session_store.bind(key):
            notifications.add("system", "hello", "")
        assert key in session_store.client_keys()

        fan_out_notifications_live()

        registry = lucky_app.app._mutable_state.signal_registry
        assert registry is not None
        assert registry.cached_value("notifications", audience_key=key) is not None


class TestExampleModuleIsolation:
    """Cross-example sys.modules collisions must not break Lucky Cat's load."""

    @pytest.mark.issue(362)
    def test_app_load_purges_foreign_pages_module(self) -> None:
        """Loading Lucky Cat must purge a sibling example's stale ``pages._context``
        so ``from pages._context import hero_chart`` resolves to OUR tree."""
        import importlib.util
        import sys
        import types
        from pathlib import Path

        here = Path(__file__).parent
        sibling_pages = here.parent / "kanban_shell" / "pages"

        # Snapshot every pages*/app entry so we can fully restore afterward.
        saved = {
            n: sys.modules.get(n)
            for n in list(sys.modules)
            if n == "pages" or n.startswith("pages.") or n == "app"
        }
        # Poison: a foreign ``pages._context`` with NO ``hero_chart`` — exactly the
        # stale module a sibling example leaves behind on a shared worker.
        fake_pkg = types.ModuleType("pages")
        fake_pkg.__file__ = str(sibling_pages / "__init__.py")
        fake_pkg.__path__ = [str(sibling_pages)]
        fake_ctx = types.ModuleType("pages._context")
        fake_ctx.__file__ = str(sibling_pages / "_context.py")
        sys.modules["pages"] = fake_pkg
        sys.modules["pages._context"] = fake_ctx

        try:
            if str(here) not in sys.path:
                sys.path.insert(0, str(here))
            from wiring.bootstrap import purge_stale_sibling_modules, purge_wiring_modules

            purge_stale_sibling_modules(here)
            purge_wiring_modules()
            spec = importlib.util.spec_from_file_location(
                "example_lucky_cat_isolation", here / "app.py"
            )
            assert spec is not None
            assert spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules["example_lucky_cat_isolation"] = module
            # Must NOT raise ImportError on ``from pages._context import hero_chart``.
            spec.loader.exec_module(module)
            assert module.app is not None
            # The real Lucky Cat pages._context (with hero_chart) is now resolved.
            assert Path(sys.modules["pages._context"].__file__).parent == (here / "pages")
        finally:
            sys.modules.pop("example_lucky_cat_isolation", None)
            for n in [n for n in list(sys.modules) if n == "pages" or n.startswith("pages.")]:
                sys.modules.pop(n, None)
            for n, mod in saved.items():
                if mod is not None:
                    sys.modules[n] = mod
