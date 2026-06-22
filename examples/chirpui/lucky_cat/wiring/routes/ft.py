"""Free-threading proof — GET /ft/stream (portfolio page SSE twin)."""

import contextlib
import sys
import time

from feed import get_feed

from chirp import EventStream, Fragment

from wiring.app_factory import app

_PORTFOLIO_TEMPLATE = "portfolio/page.html"


def register(app_instance) -> None:
    @app_instance.route("/ft/stream", referenced=True)
    def ft_stream():
        feed = get_feed()
        symbols = [m.symbol for m in feed.markets()]
        gil_enabled = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
        workers = getattr(feed, "worker_count", 0)
        markets = getattr(feed, "market_count", len(symbols))

        async def generate():
            if not symbols:
                return
            last_count = feed.tick_count() if hasattr(feed, "tick_count") else 0
            last_ts = time.monotonic()
            with contextlib.suppress(KeyError):
                async for _tick in feed.subscribe(symbols[0]):
                    now = feed.tick_count() if hasattr(feed, "tick_count") else last_count
                    wall = time.monotonic()
                    elapsed = wall - last_ts
                    rate = round((now - last_count) / elapsed, 1) if elapsed > 0 else 0.0
                    last_count, last_ts = now, wall
                    yield Fragment(
                        _PORTFOLIO_TEMPLATE,
                        "ft_panel_oob",
                        ft_gil_enabled=gil_enabled,
                        ft_workers=workers,
                        ft_markets=markets,
                        ft_ticks_per_sec=rate,
                    )

        return EventStream(generate())
