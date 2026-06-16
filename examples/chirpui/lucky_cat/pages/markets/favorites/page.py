"""Favorites — GET /markets/favorites.

The starred-only view of the markets grid — one of the four FIXED Markets
destinations (Home / Favorites / Trending / Research). Moved here from the old
``/watchlist`` route (#282); the rail's Favorites lane links here and the live
``#watchlist-count`` badge OOB still updates after a star toggle on any page.

It reuses the landing grid's ``market_grid`` def (single source of truth for the
card markup + the per-card star) over the markets the user has starred via the
``/watchlist/toggle`` route, with a polished empty state when nothing is starred.

``markets`` / ``tickers`` / ``sparklines`` / ``watchlist_starred`` all flow in
from the root ``_context.py``; this handler filters them to the starred set so
the grid renders only the starred markets (the star on each still toggles, so a
user can unstar from here too — the OOB twin flips the control in place).
"""

from chirp import Page, login_required


@login_required
def get(markets, tickers, sparklines, watchlist_starred) -> Page:
    # Filter the full markets list to the starred set, preserving the canonical
    # market order (so favorites read in the same order as the landing grid).
    starred_markets = tuple(m for m in markets if m.symbol in watchlist_starred)
    return Page(
        "markets/favorites/page.html",
        "page_content",
        page_block_name="page_root",
        starred_markets=starred_markets,
        tickers=tickers,
        sparklines=sparklines,
        watchlist_starred=watchlist_starred,
    )
