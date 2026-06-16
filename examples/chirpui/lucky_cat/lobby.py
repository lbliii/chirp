"""The Markets Home lobby context for Lucky Cat (#281, PR7).

The curated, **bounded** Markets landing — one of the five fixed Markets
destinations (Home / Favorites / Trending / Research / Coin). It is NOT the full
catalog: a stat strip, a small top-movers preview, a watchlist preview, a
featured market, and a CTA into Research (the scalable home for 500+ coins). The
full grid is retired here — it lived on the old ``GET /`` landing and is
superseded by Research's server-side filter/sort/paginate surface.

Rendered by BOTH ``GET /`` (``pages/page.py``) and ``GET /markets``
(``pages/markets/page.py``) via the SAME ``markets/page.html`` template — ``/`` is
an **alias** for ``/markets`` (the RFC's canonical-home decision: alias, no
redirect, no round-trip, no ``href='/'`` churn). The shared :func:`lobby_context`
is the single source of truth so the two routes can never drift.

Data layer (PR4): the numbers come from ``research.build_rows(markets, tickers)``
(the single source of truth shared with Trending / Research) ranked by
``ranking.top_gainers / top_losers / top_volume`` + ``ranking.market_stats`` — so
the lobby figures match every other Markets surface exactly. Pure + deterministic
(stable total-order ranks), no I/O.

DUPLICATE-ID FOOTGUN (RFC §risks): a coin that appears in BOTH the movers preview
AND the watchlist preview (or the featured slot) would render
``#luckycat-card-{symbol}`` / ``#watchlist-star-{symbol}`` twice — invalid HTML
that breaks ``getElementById`` AND the ``/watchlist/toggle`` unstar-prune target
(``hx-swap-oob="delete"`` on ``#luckycat-card-{symbol}``). So the regions that
emit those ids — the featured card and the watchlist-preview cards — are de-duped
HERE: the featured symbol is removed from the watchlist preview, and the movers
preview is rendered as compact rows (coin-detail LINKS, never ``market_card``), so
it carries no card/star ids at all and can never collide with the card regions.
"""

from __future__ import annotations

from dataclasses import dataclass

import ranking
import research
from research import Row

# How many movers each segment shows in the bounded preview (the full top-N
# leaderboard lives on Trending). Three each keeps the lobby ~9 cards.
_PREVIEW_N = 3
# How many starred markets the watchlist preview shows before it points the user
# at the full Favorites view.
_WATCHLIST_PREVIEW_N = 3


@dataclass(frozen=True, slots=True)
class MoverPreview:
    """One compact movers-preview segment (Gainers / Losers / Volume).

    ``rows`` is rendered as coin-detail LINKS (never ``market_card``), so this
    region carries no ``#luckycat-card-{symbol}`` / ``#watchlist-star-{symbol}``
    ids and can never collide with the card-bearing regions (the duplicate-id
    footgun). ``href`` is the Trending segment this preview teases.
    """

    key: str
    label: str
    href: str
    rows: tuple[Row, ...]


def lobby_context(
    markets: tuple,
    tickers: dict,
    sparklines: dict,
    watchlist_starred: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> dict:
    """Build the curated, de-duped Home-lobby context shared by ``/`` + ``/markets``.

    * **Stat strip** — ``ranking.market_stats`` over the PR4 rows.
    * **Movers preview** — ``ranking.top_gainers/losers/volume`` (a few each),
      rendered as links (no card ids) into the Trending segments.
    * **Watchlist preview** — the user's starred markets (capped), rendered as
      cards, de-duped against the featured symbol.
    * **Featured** — the catalog's top gainer (the headline coin), rendered as a
      card; ``None`` for an empty catalog.

    Pure + deterministic: the underlying ranks are stable total-order sorts, so
    the same inputs yield the same lobby every call (the goldens hold).
    """
    starred = frozenset(watchlist_starred)
    rows = research.build_rows(tuple(markets), tickers)
    by_symbol = {m.symbol: m for m in markets}

    stats = ranking.market_stats(rows)

    movers = (
        MoverPreview(
            key="gainers",
            label="Gainers",
            href="/markets/trending?seg=gainers",
            rows=ranking.top_gainers(rows, _PREVIEW_N),
        ),
        MoverPreview(
            key="losers",
            label="Losers",
            href="/markets/trending?seg=losers",
            rows=ranking.top_losers(rows, _PREVIEW_N),
        ),
        MoverPreview(
            key="volume",
            label="Volume",
            href="/markets/trending?seg=volume",
            rows=ranking.top_volume(rows, _PREVIEW_N),
        ),
    )

    # Featured: the catalog's top gainer (the headline mover). Rendered as a card,
    # so its #luckycat-card-{symbol} / #watchlist-star-{symbol} ids must not repeat
    # anywhere else on the page.
    featured_row = stats.top_gainer
    featured_symbol = featured_row.symbol if featured_row is not None else None
    featured_market = by_symbol.get(featured_symbol) if featured_symbol is not None else None

    # Watchlist preview: the starred markets in canonical catalog order, capped,
    # and DE-DUPED against the featured symbol so the same card id never renders
    # twice (the duplicate-id footgun). Markets that vanished from the catalog
    # (stale star) are skipped — only real markets render a card.
    starred_markets = tuple(
        m for m in markets if m.symbol in starred and m.symbol != featured_symbol
    )[:_WATCHLIST_PREVIEW_N]

    return {
        "stats": stats,
        "movers": movers,
        "featured_market": featured_market,
        "featured_row": featured_row,
        "watchlist_preview": starred_markets,
        "watchlist_starred": starred,
        "tickers": tickers,
        "sparklines": sparklines,
        # The CTA destination — the scalable full catalog.
        "research_href": "/markets/research",
        "trending_href": "/markets/trending",
        "favorites_href": "/markets/favorites",
    }
