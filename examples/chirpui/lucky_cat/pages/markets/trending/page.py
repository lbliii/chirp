"""Markets → Trending — GET /markets/trending (#279).

The third fixed Markets destination: a leaderboard of the catalog's movers
across three segments — **Gainers** (highest 24h change), **Losers** (lowest),
and **Volume** (highest notional 24h volume). The segmented control swaps the
``#movers-region`` in place via htmx; everything else is the boosted shell.

Data layer (PR4): the rows come from ``research.build_rows(markets, tickers)``
(the single source of truth shared with Home / Research) and the ordering from
``ranking.top_gainers / top_losers / top_volume`` — so the numbers and the order
match every other Markets surface exactly.

**Snapshot-per-swap (RFC decision, no live re-rank).** Each segment swap reads a
*fresh* snapshot of the catalog and re-ranks it; there is no live SSE reorder. A
live reorder would fight htmx swap semantics and churn star state on every tick;
a ``signal()``-backed live version is noted as a future enhancement, not this
issue. Because ``ranking`` uses stable total-order sorts (rank key, then symbol
ascending), the same snapshot ranks identically every call.

FOOTGUN #2 (boosted-shell self-override): each segment toggle lives INSIDE the
boosted shell, so it inherits ``hx-target=#main`` / ``hx-select=#page-content``
from the ancestors. Each toggle OVERRIDES those to ``hx-target=#movers-region`` +
``hx-select=#movers-region`` (see page.html), and this handler re-emits the SAME
``#movers-region`` wrapper for the swap — otherwise the inherited
``#page-content`` is absent from the fragment and the swap lands EMPTY. The
segment swap is detected by the ``HX-Target`` header (``movers-region``) so a
boosted full-page nav still renders the whole shell.

Routing footgun: this resolves as the STATIC child ``markets/trending`` of the
filesystem router, NOT captured by the sibling ``{symbol}`` dynamic segment —
proven by ``app.check()`` + an explicit ``GET == 200`` test.
"""

from __future__ import annotations

import ranking
import research

from chirp import Fragment, Page, Request

# The closed set of segments (param value -> human label + ranking function). A
# closed map so a hand-typed ``?seg=`` can never reach an arbitrary callable; an
# unknown / missing segment clamps to the default below.
_SEGMENTS: dict[str, tuple[str, object]] = {
    "gainers": ("Gainers", ranking.top_gainers),
    "losers": ("Losers", ranking.top_losers),
    "volume": ("Volume", ranking.top_volume),
}
_SEGMENT_ORDER: tuple[str, ...] = ("gainers", "losers", "volume")
DEFAULT_SEGMENT = "gainers"

# Leaderboard depth — how many movers each segment shows.
_TOP_N = 10

# The DOM id the segment toggles target (FOOTGUN #2 self-override + fragment
# re-emit). Kept here so the handler and the template agree on one literal.
_MOVERS_REGION_ID = "movers-region"


def _clamp_segment(value: str | None) -> str:
    """Clamp a raw ``?seg=`` value into the closed segment set."""
    seg = (value or "").strip().lower()
    return seg if seg in _SEGMENTS else DEFAULT_SEGMENT


def _movers_context(active: str, markets, tickers) -> dict:
    """Build the snapshot-per-swap context for the ``#movers-region``.

    Reads a FRESH catalog snapshot (``build_rows``) and re-ranks it for the
    active segment — no cached/live order, so each swap is a clean snapshot.
    """
    rows = research.build_rows(tuple(markets), tickers)
    label, ranker = _SEGMENTS[active]
    return {
        "active_segment": active,
        "segments": _SEGMENT_ORDER,
        "segment_labels": {key: _SEGMENTS[key][0] for key in _SEGMENT_ORDER},
        "active_label": label,
        "movers": ranker(rows, _TOP_N),
    }


def get(request: Request, markets, tickers) -> Page | Fragment:
    active = _clamp_segment(request.query.get("seg"))
    ctx = _movers_context(active, markets, tickers)

    # FOOTGUN #2: the segment toggles self-override hx-target/hx-select to
    # #movers-region, so a segment swap arrives with HX-Target=movers-region.
    # Re-emit ONLY that wrapper (a bare Fragment passes through with no layout),
    # so htmx's hx-select="#movers-region" finds its own region in the response.
    # Any other request (browser nav, boosted shell swap) renders the full page.
    if request.htmx and request.htmx.target == _MOVERS_REGION_ID:
        return Fragment("markets/trending/page.html", "movers_region", **ctx)

    return Page(
        "markets/trending/page.html",
        "page_content",
        page_block_name="page_root",
        **ctx,
    )
