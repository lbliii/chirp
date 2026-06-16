"""Market detail — GET /markets/{symbol}.

Renders the live trading view for one market — ticker (price + 24h change),
order-book depth (bids/asks), and the recent-trades tape — all from the
:class:`~feed.FeedSource` snapshot. The same template blocks
(``market_ticker`` / ``order_book`` / ``trade_tape``) render here for browser
navigation and are re-rendered as OOB fragments by the SSE stream in app.py.

The hero area chart geometry is precomputed server-side (DOMAIN — see
``pages._context.hero_chart``). The segmented timeframe toggle ``hx-get``s
``/markets/{symbol}/chart`` and swaps the ``#market-chart`` region.

Unknown symbols return 404 as a tuple ``(message, 404)``. The page template name
keeps the literal ``{symbol}`` segment — that is the mounted template key, not
an f-string.
"""

from feed import DEFAULT_INTERVAL, INTERVALS, get_feed
from pages._context import HeroChart, hero_chart

from chirp import Page

# Hero chart sample budget — taller than the grid sparkline so the focal-point
# area chart reads as the screen's anchor without re-sampling the candle ring.
_HERO_CANDLES = 64


def build_hero_chart(symbol: str, feed, interval: str = DEFAULT_INTERVAL) -> HeroChart:
    """Gradient-area hero chart geometry + crosshair data for one timeframe.

    Reuses the landing grid's sparkline geometry (a fixed 100x36 viewBox,
    stretched to the hero with preserveAspectRatio="none") so the up/down jade-
    red direction and the points-string contract never drift between the card
    spark and the detail hero. Returns ``ok=False`` (template skips the SVG)
    when there are too few candles to draw a shape. Shared by the full-page
    render here and the ``/markets/{symbol}/chart`` timeframe-toggle fragment in
    app.py so the two renders can never diverge.
    """
    closes = tuple(c.close for c in feed.candles(symbol, interval=interval, limit=_HERO_CANDLES))
    return hero_chart(closes, interval)


def get(symbol: str):
    feed = get_feed()
    # SimFeed exposes has_symbol; fall back to scanning markets() for any
    # FeedSource that does not.
    known = (
        feed.has_symbol(symbol)
        if hasattr(feed, "has_symbol")
        else any(m.symbol == symbol for m in feed.markets())
    )
    if not known:
        return ("Market not found", 404)

    # The Market def (base / quote / display_name) for the static Info panel — the
    # inner rail's "this market" lane has an Info anchor (#info), so the page must
    # ship a real id="info" section for it (no FeedSource single-market accessor,
    # so scan the small markets() tuple once).
    market = next((m for m in feed.markets() if m.symbol == symbol), None)

    return Page(
        "markets/{symbol}/page.html",
        "page_content",
        page_block_name="page_root",
        symbol=symbol,
        market=market,
        ticker=feed.ticker(symbol),
        book=feed.order_book(symbol),
        trades=feed.trades(symbol),
        candles=feed.candles(symbol),
        hero_chart=build_hero_chart(symbol, feed, DEFAULT_INTERVAL),
        chart_interval=DEFAULT_INTERVAL,
        chart_intervals=INTERVALS,
    )
