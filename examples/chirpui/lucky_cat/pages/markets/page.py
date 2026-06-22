"""Markets Home — GET /markets, the curated lobby (#281, PR7).

The canonical Markets landing: a CURATED, BOUNDED lobby (~9 cards), NOT the full
catalog. A stat strip (``ranking.market_stats``), a top-movers preview
(``ranking.top_gainers/losers/volume``, a few each), a watchlist preview (the
starred set), a featured market, and a CTA into Research (``/markets/research``,
the scalable home for the full 500+ coin catalog). The full grid that the old
``GET /`` landing shipped is RETIRED — superseded by Research + this lobby.

``/`` is an ALIAS for ``/markets`` (the RFC's canonical-home decision: alias, no
redirect). ``pages/page.py`` (the ``GET /`` handler) renders this SAME
``markets/page.html`` template from the SAME shared :func:`lobby.lobby_context`,
so both routes render an identical lobby and can never drift.

``markets`` / ``tickers`` / ``sparklines`` / ``watchlist_starred`` flow in from
the root ``_context.py``; :func:`lobby.lobby_context` ranks them (via the PR4
``research`` / ``ranking`` seam) and DE-DUPES the card regions so a coin in both
the featured slot and the watchlist preview never duplicates
``#luckycat-card-{symbol}`` / ``#watchlist-star-{symbol}`` (the no-duplicate-id
invariant + the unstar-prune target).

Routing footgun: this resolves as the STATIC child ``markets`` (the bare
``/markets``) of the filesystem router, NOT captured by the sibling ``{symbol}``
dynamic segment (which only matches ``/markets/<x>``) — proven by ``app.check()``
+ an explicit ``GET /markets == 200`` test.
"""

import lobby

from chirp import Page, Request


def get(markets, tickers, sparklines, watchlist_starred) -> Page:
    ctx = lobby.lobby_context(markets, tickers, sparklines, watchlist_starred)
    return Page(
        "markets/page.html",
        "page_content",
        page_block_name="page_root",
        **ctx,
    )


async def post(request: Request, markets, tickers, sparklines, watchlist_starred) -> Page:
    """Fallback — deposit dispatches via ``pages/markets/_actions.py`` (_action field)."""
    return get(markets, tickers, sparklines, watchlist_starred)
