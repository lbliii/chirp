"""Markets → Research — GET /markets/research (#280, PR6).

The fourth fixed Markets destination and the **power surface** for 500+ coins:
search + facet filters (sector / price / change / volume bands) + sortable
column headers + **server-side pagination** + a lightweight server-rendered
compare. Everything is URL-param-driven (``?q=&sort=&dir=&page=&sector=`` plus
the ``price``/``change``/``vol`` band keys and ``cmp`` for the compare tray), so
a control change is just a new querystring and the whole surface is
bookmarkable / back-button-correct.

Data layer (PR4): the rows come from ``research.build_rows(markets, tickers)``
(the single source of truth shared with Home / Trending) and the filter ->
stable-sort -> slice happens entirely server-side in ``research.query_catalog``,
so the template renders only ``page_size`` rows regardless of how big the
catalog grows. Search shares ``search.matches`` (``query_catalog`` already calls
it), so Cmd-K and Research can never drift on what counts as a match.

Every control's ``hx-get`` URL is built **here**, in pure Python (the
``research_url`` helper + the ``*_chips`` / ``columns`` view-models), NOT in the
template — so the querystring logic (param preservation, page-reset, dir-toggle,
compare add/remove) is unit-testable and the template stays declarative.

FOOTGUN #2 (boosted-shell self-override, CRITICAL): every search / sort /
filter / paginate / compare control lives INSIDE the boosted shell, so it
inherits ``hx-target=#main`` / ``hx-select=#page-content`` from the ancestors.
Each control OVERRIDES those to ``hx-target=#research-results`` +
``hx-select=#research-results`` (see page.html), and this handler re-emits the
SAME ``#research-results`` wrapper for the swap — otherwise the inherited
``#page-content`` is absent from the fragment and the swap lands EMPTY. The
control swap is detected by the ``HX-Target`` header (``research-results``) so a
boosted full-page nav still renders the whole shell.

Routing footgun: this resolves as the STATIC child ``markets/research`` of the
filesystem router, NOT captured by the sibling ``{symbol}`` dynamic segment —
proven by ``app.check()`` + an explicit ``GET == 200`` test. ``research`` is
never treated as a coin.
"""

from __future__ import annotations

from urllib.parse import urlencode

import research

from chirp import Fragment, Page, Request

# The DOM id every Research control targets (FOOTGUN #2 self-override + fragment
# re-emit). Kept here so the handler and the template agree on one literal.
_RESULTS_REGION_ID = "research-results"
_PATH = "/markets/research"

# Closed facet maps (param value -> human label + the band passed to
# query_catalog). Closed sets so a hand-typed ``?price=`` / ``?change=`` /
# ``?vol=`` can never reach an arbitrary band; an unknown / missing value clamps
# to the "all" key (an empty string), which applies no filter. Bands are
# inclusive ``(min, max)`` with ``None`` meaning unbounded on that side — exactly
# what ``research._in_range`` consumes.
_PRICE_BANDS: dict[str, tuple[str, tuple[float | None, float | None] | None]] = {
    "": ("Any price", None),
    "lt1": ("< 1 $MEOW", (None, 1.0)),
    "1to100": ("1 - 100", (1.0, 100.0)),
    "gt100": ("> 100 $MEOW", (100.0, None)),
}
_PRICE_ORDER: tuple[str, ...] = ("", "lt1", "1to100", "gt100")

# ``up`` / ``down`` are single bands; ``big`` is a ±5% UNION (either tail) that a
# single ``(min, max)`` band cannot express, so it is special-cased in the
# handler (pre-filter the input rows). Its band entry is ``None``.
_CHANGE_BANDS: dict[str, tuple[str, tuple[float | None, float | None] | None]] = {
    "": ("Any 24h", None),
    "up": ("Gainers", (0.0001, None)),
    "down": ("Losers", (None, -0.0001)),
    "big": ("Movers ±5%", None),
}
_CHANGE_ORDER: tuple[str, ...] = ("", "up", "down", "big")
_CHANGE_BIG_THRESHOLD = 5.0

_VOL_BANDS: dict[str, tuple[str, tuple[float | None, float | None] | None]] = {
    "": ("Any volume", None),
    "lt10k": ("< 10k", (None, 10_000.0)),
    "10kto1m": ("10k - 1M", (10_000.0, 1_000_000.0)),
    "gt1m": ("> 1M", (1_000_000.0, None)),
}
_VOL_ORDER: tuple[str, ...] = ("", "lt10k", "10kto1m", "gt1m")

# Sortable column headers (param value -> human label). The param is clamped to
# research.SORT_KEYS inside query_catalog, so an out-of-set ``?sort=`` is safe;
# this map only drives the rendered header labels + active-state.
_SORT_LABELS: dict[str, str] = {
    "symbol": "Market",
    "name": "Name",
    "price": "Price",
    "change": "24h",
    "volume": "Volume",
}
_COLUMN_ORDER: tuple[str, ...] = ("symbol", "name", "price", "change", "volume")

# Compare tray cap — keep it simple (a handful of pinned coins, server-rendered).
_COMPARE_MAX = 4


def _clamp(value: str | None, order: tuple[str, ...]) -> str:
    """Clamp a raw facet param into a closed key set (default = ``""`` = all)."""
    key = (value or "").strip().lower()
    return key if key in order else ""


def _clamp_int(value: str | None, default: int) -> int:
    """Parse a 1-based ``?page=`` int; any garbage clamps to ``default`` (>= 1)."""
    try:
        n = int((value or "").strip())
    except TypeError, ValueError:
        return default
    return n if n >= 1 else default


def _parse_compare(value: str | None, known: frozenset[str]) -> tuple[str, ...]:
    """Parse the ``?cmp=`` comma list into a deduped, known-only, capped tuple.

    Order-preserving (first-seen wins), filtered to symbols that exist in the
    catalog, and capped at :data:`_COMPARE_MAX` so a hand-typed ``?cmp=`` can
    never pin an unbounded / unknown set.
    """
    out: list[str] = []
    for raw in (value or "").split(","):
        sym = raw.strip().upper()
        if sym and sym in known and sym not in out:
            out.append(sym)
        if len(out) >= _COMPARE_MAX:
            break
    return tuple(out)


def research_url(state: dict[str, str], **overrides: str) -> str:
    """A Research URL with the active ``state`` merged over by ``overrides``.

    The single source of truth for EVERY control's ``hx-get`` (so the param
    preservation can never drift between the search box, the facet chips, the
    sort headers, the pager, and the compare links). Empty values are dropped so
    the URL stays clean, the params emit in a stable order (so a given state maps
    to one canonical URL — handy in tests), and a control change resets to page 1
    UNLESS the override sets ``page`` itself (the pager does).
    """
    merged = {**state, **overrides}
    if "page" not in overrides:
        merged.pop("page", None)  # any filter/sort/search lands on page 1
    ordered = ("q", "sector", "sort", "dir", "price", "change", "vol", "page", "cmp")
    pairs = [(k, merged[k]) for k in ordered if merged.get(k)]
    qs = urlencode(pairs)
    return f"{_PATH}?{qs}" if qs else _PATH


def _research_context(request: Request, markets, tickers) -> dict:
    """Build the full Research context from the URL params + the PR4 query seam.

    Reads a FRESH catalog snapshot (``build_rows``), parses + clamps every param,
    runs ``query_catalog`` server-side (filter -> stable-sort -> slice), and
    builds the per-control view-models (every ``hx-get`` URL precomputed via
    :func:`research_url`). Used for BOTH the full-page render and the
    ``#research-results`` control swap, so the two renders can never diverge.
    """
    rows = research.build_rows(tuple(markets), tickers)
    by_symbol = {r.symbol: r for r in rows}
    known = frozenset(by_symbol)

    q = (request.query.get("q") or "").strip()
    sort_key = (request.query.get("sort") or research.DEFAULT_SORT).strip().lower()
    sort_dir = (request.query.get("dir") or research.DEFAULT_DIR).strip().lower()
    page = _clamp_int(request.query.get("page"), 1)

    price_key = _clamp(request.query.get("price"), _PRICE_ORDER)
    change_key = _clamp(request.query.get("change"), _CHANGE_ORDER)
    vol_key = _clamp(request.query.get("vol"), _VOL_ORDER)

    # Sector filter is exact-match against the static taxonomy; only offer the
    # sectors actually present in the catalog (plus the "all" sentinel). An
    # unknown / stale ?sector= clamps to "all".
    sectors_present = tuple(sorted({r.sector for r in rows}))
    sector = (request.query.get("sector") or "").strip()
    if sector not in sectors_present:
        sector = ""

    price_range = _PRICE_BANDS[price_key][1]
    vol_range = _VOL_BANDS[vol_key][1]
    change_special = change_key == "big"
    change_band = None if change_special else _CHANGE_BANDS[change_key][1]

    # "big" (±5% movers) is a union of both tails, which one (min,max) band can't
    # express — so pre-filter the INPUT rows to |change| >= threshold and let the
    # seam do the rest. Still entirely server-side + deterministic (the stable
    # sort is preserved because we only narrow the input set up front), and paging
    # / totals stay correct because query_catalog slices the filtered set.
    catalog = (
        tuple(r for r in rows if abs(r.change_pct) >= _CHANGE_BIG_THRESHOLD)
        if change_special
        else rows
    )

    result = research.query_catalog(
        catalog,
        q=q,
        sector=sector,
        price_range=price_range,
        change_band=change_band,
        vol_range=vol_range,
        sort_key=sort_key,
        sort_dir=sort_dir,
        page=page,
    )

    compare = _parse_compare(request.query.get("cmp"), known)

    # The canonical active state every control URL preserves. sort/dir read the
    # clamped values back off the result so a tampered ?sort= doesn't leak into
    # the links.
    state = {
        "q": q,
        "sector": sector,
        "sort": result.sort_key,
        "dir": result.sort_dir,
        "price": price_key,
        "change": change_key,
        "vol": vol_key,
        "cmp": ",".join(compare),
    }

    # --- per-control view-models (every hx-get URL precomputed) ---------------
    # Each facet group changes exactly one param; map the group to its param name.
    def _facet_chips(param, order, bands, active):
        return tuple(
            {
                "key": k,
                "label": bands[k][0],
                "active": k == active,
                "url": research_url(state, **{param: k}),
            }
            for k in order
        )

    sector_chips = (
        {
            "key": "",
            "label": "All",
            "active": sector == "",
            "url": research_url(state, sector=""),
        },
        *(
            {
                "key": s,
                "label": s,
                "active": s == sector,
                "url": research_url(state, sector=s),
            }
            for s in sectors_present
        ),
    )

    columns = tuple(
        {
            "key": col,
            "label": _SORT_LABELS[col],
            "active": col == result.sort_key,
            "dir": result.sort_dir if col == result.sort_key else "",
            # Toggle direction when re-clicking the active column; default desc.
            "url": research_url(
                state,
                sort=col,
                dir=(
                    ("asc" if result.sort_dir == "desc" else "desc")
                    if col == result.sort_key
                    else "desc"
                ),
            ),
        }
        for col in _COLUMN_ORDER
    )

    # Per-row view-model — the Row plus its compare pin/unpin URLs + pinned flag
    # baked in. URLs are precomputed here (NOT via a callable in the template
    # context, which Chirp's sandbox may refuse to call) so the template just
    # emits ``row.pin_url`` / ``row.unpin_url``. ``pin_url`` adds this symbol;
    # ``unpin_url`` drops it (used by both the table row and the compare tray).
    compare_set = frozenset(compare)

    def _pin_url(symbol: str) -> str:
        return research_url(state, cmp=",".join((*compare, symbol)))

    def _unpin_url(symbol: str) -> str:
        return research_url(state, cmp=",".join(s for s in compare if s != symbol))

    row_views = tuple(
        {
            "row": r,
            "pinned": r.symbol in compare_set,
            "pin_url": _pin_url(r.symbol),
            "unpin_url": _unpin_url(r.symbol),
        }
        for r in result.rows
    )
    compare_views = tuple({"row": by_symbol[s], "unpin_url": _unpin_url(s)} for s in compare)

    return {
        "result": result,
        "rows": row_views,
        "q": q,
        "sector": sector,
        "sort_key": result.sort_key,
        "sort_dir": result.sort_dir,
        "columns": columns,
        "sector_chips": sector_chips,
        "price_chips": _facet_chips("price", _PRICE_ORDER, _PRICE_BANDS, price_key),
        "change_chips": _facet_chips("change", _CHANGE_ORDER, _CHANGE_BANDS, change_key),
        "vol_chips": _facet_chips("vol", _VOL_ORDER, _VOL_BANDS, vol_key),
        "compare": compare,
        "compare_rows": compare_views,
        "compare_max": _COMPARE_MAX,
        "compare_full": len(compare) >= _COMPARE_MAX,
        "compare_clear_url": research_url(state, cmp=""),
        "search_hidden": state,  # the search form re-submits the active state
        "prev_url": research_url(state, page=str(result.page - 1)) if result.has_prev else "",
        "next_url": research_url(state, page=str(result.page + 1)) if result.has_next else "",
    }


def get(request: Request, markets, tickers) -> Page | Fragment:
    ctx = _research_context(request, markets, tickers)

    # FOOTGUN #2: every control self-overrides hx-target/hx-select to
    # #research-results, so a control swap arrives with HX-Target=research-results.
    # Re-emit ONLY that wrapper (a bare Fragment passes through with no layout),
    # so htmx's hx-select="#research-results" finds its own region in the
    # response. Any other request (browser nav, boosted shell swap) renders the
    # full page.
    if request.htmx and request.htmx.target == _RESULTS_REGION_ID:
        return Fragment("markets/research/page.html", "research_results", **ctx)

    return Page(
        "markets/research/page.html",
        "page_content",
        page_block_name="page_root",
        **ctx,
    )
