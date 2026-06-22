"""Market detail SSE + chart fragments — referenced=True htmx/SSE-only routes."""

import contextlib

from feed import DEFAULT_INTERVAL, INTERVALS, get_feed

from chirp import EventStream, Fragment, Request

_DETAIL_TEMPLATE = "markets/{symbol}/page.html"


def _hero_chart(closes: tuple[float, ...], interval: str):
    from pages._context import hero_chart

    return hero_chart(closes, interval)


def register(app_instance) -> None:
    @app_instance.route("/markets/{symbol}/chart", referenced=True)
    def market_chart(symbol: str, request: Request):
        feed = get_feed()
        known = (
            feed.has_symbol(symbol)
            if hasattr(feed, "has_symbol")
            else any(m.symbol == symbol for m in feed.markets())
        )
        if not known:
            return ("Market not found", 404)

        requested = (request.query.get("tf") or "").strip()
        interval = requested if requested in INTERVALS else DEFAULT_INTERVAL
        closes = tuple(c.close for c in feed.candles(symbol, interval=interval, limit=64))
        return Fragment(
            _DETAIL_TEMPLATE,
            "chart_region",
            symbol=symbol,
            hero_chart=_hero_chart(closes, interval),
            chart_interval=interval,
            chart_intervals=INTERVALS,
        )

    @app_instance.route("/markets/{symbol}/stream", referenced=True)
    def market_stream(symbol: str):
        feed = get_feed()
        known = (
            feed.has_symbol(symbol)
            if hasattr(feed, "has_symbol")
            else any(m.symbol == symbol for m in feed.markets())
        )

        async def generate():
            if not known:
                return
            with contextlib.suppress(KeyError):
                async for tick in feed.subscribe(symbol):
                    yield Fragment(
                        _DETAIL_TEMPLATE,
                        "market_ticker_oob",
                        symbol=symbol,
                        ticker=tick.ticker,
                    )
                    yield Fragment(
                        _DETAIL_TEMPLATE,
                        "order_book_oob",
                        symbol=symbol,
                        book=tick.book,
                    )
                    yield Fragment(
                        _DETAIL_TEMPLATE,
                        "trade_tape_oob",
                        symbol=symbol,
                        trades=tick.trades,
                    )

        return EventStream(generate())
