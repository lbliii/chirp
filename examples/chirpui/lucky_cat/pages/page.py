"""Markets Home alias — GET /.

``/`` is an ALIAS for ``/markets`` (the RFC's canonical-home decision: alias, no
redirect, no round-trip, no ``href='/'`` churn). It renders the SAME curated lobby
``markets/page.html`` from the SAME shared :func:`lobby.lobby_context` as
``pages/markets/page.py``, so both routes render an identical lobby and can never
drift.

The old full markets grid that used to live here (#222) is RETIRED — the bounded
lobby (stat strip + movers/watchlist previews + featured + a Research CTA) plus
Research's server-side full catalog supersede it. ``markets`` / ``tickers`` /
``sparklines`` / ``watchlist_starred`` flow in from the root ``_context.py``.
"""

import lobby

from chirp import Page


def get(markets, tickers, sparklines, watchlist_starred) -> Page:
    ctx = lobby.lobby_context(markets, tickers, sparklines, watchlist_starred)
    return Page(
        "markets/page.html",
        "page_content",
        page_block_name="page_root",
        **ctx,
    )
