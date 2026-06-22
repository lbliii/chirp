"""Live ``FeedSource`` adapters for Lucky Cat (#226).

Selected via ``LUCKY_CAT_FEED`` (``sim`` default). Each adapter implements the
``FeedSource`` protocol from ``feed.py``; optional deps are ``websockets`` (WS
feeds) and ``httpx`` (REST poll). Import or connect failures return ``None`` so
``feed._build_feed()`` can fall back to the deterministic ``SimFeed``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from feed import FeedSource

logger = logging.getLogger("lucky_cat.feed")


def build_adapter(name: str) -> FeedSource | None:
    """Construct a live feed for ``name``, or ``None`` when unavailable."""
    key = name.strip().lower()
    if key == "kraken":
        try:
            import websockets  # noqa: F401
        except ImportError:
            logger.warning("KrakenFeed requires websockets; install websockets to enable.")
            return None
        from feed_adapters.kraken import KrakenFeed

        return KrakenFeed()
    if key == "coingecko":
        try:
            import httpx  # noqa: F401
        except ImportError:
            logger.warning("CoinGeckoFeed requires httpx; install httpx to enable.")
            return None
        from feed_adapters.coingecko import CoinGeckoFeed

        return CoinGeckoFeed()
    if key == "mempool":
        try:
            import websockets  # noqa: F401
        except ImportError:
            logger.warning("MempoolFeed requires websockets; install websockets to enable.")
            return None
        from feed_adapters.mempool import MempoolFeed

        return MempoolFeed()
    if key in ("coinbase", "binance"):
        logger.warning(
            "LUCKY_CAT_FEED=%r is not implemented (Binance is US-geoblocked on "
            "common cloud regions); use kraken or coingecko.",
            name,
        )
        return None
    logger.warning("LUCKY_CAT_FEED=%r is unknown.", name)
    return None
