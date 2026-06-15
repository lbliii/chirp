"""The Markets research/query seam for Lucky Cat (#277).

The single source of truth that filters, sorts, and slices the market catalog
**server-side** so a template renders only one page of rows regardless of how
big the catalog is (the scalable home for 500+ coins lives in
``pages/markets/research``). Home (``pages/markets``) and Trending
(``pages/markets/trending``) read the same :class:`Row` view via
:func:`build_rows`, so the four Markets surfaces never disagree about a coin's
price / 24h change / volume / sector.

Design (locked in the RFC):

* **Pure & deterministic** — no I/O, frozen dataclasses, stable total-order
  sorts (sort key, then symbol as an always-ascending tiebreaker). Same input =>
  same :class:`QueryResult`, so the goldens hold.
* **Sector is a static map here** — NOT a field on the ``feed.Market``
  dataclass (that would ripple into the determinism golden + every consumer).
* **Volume is notional** — quote-denominated (``price * base_volume``) so a
  cheap, high-unit-count meme coin doesn't dominate a "top volume" view; the
  raw per-trade size volume on the ticker is base units and is not comparable
  across markets.
* **Substring search delegates to :mod:`search`** — the same matcher Cmd-K uses.
"""

from __future__ import annotations

from dataclasses import dataclass

from search import matches

# Static sector taxonomy, keyed by the market BASE asset (BTC / ETH / ...). A
# map here keeps it out of the frozen feed.Market (and the determinism golden).
# Unknown bases (e.g. an env-gated synthetic catalog, #278) fall back to "Other".
SECTORS: dict[str, str] = {
    "BTC": "Store of Value",
    "ETH": "Smart Contract",
    "SOL": "Smart Contract",
    "DOGE": "Meme",
    "PAW": "Meme",
    "KOBAN": "House",
}
DEFAULT_SECTOR = "Other"

# The sortable columns the Research surface exposes (param value -> Row key). A
# closed set so a hand-typed ``?sort=`` can never reach an arbitrary attribute.
SORT_KEYS: tuple[str, ...] = ("symbol", "name", "price", "change", "volume")
DEFAULT_SORT = "volume"
DEFAULT_DIR = "desc"
DEFAULT_PAGE_SIZE = 25


def sector_for(base: str) -> str:
    """The sector label for a market's base asset (``"Other"`` when unmapped)."""
    return SECTORS.get(base.upper(), DEFAULT_SECTOR)


@dataclass(frozen=True, slots=True)
class Row:
    """One catalog row — the flat, render-ready view of a market + its ticker.

    ``volume`` is **notional** 24h volume in the quote token ($MEOW), so it is
    comparable across markets. ``change_pct`` is the signed 24h percentage.
    """

    symbol: str
    name: str
    base: str
    price: float
    change_pct: float
    volume: float
    sector: str


@dataclass(frozen=True, slots=True)
class QueryResult:
    """One page of a catalog query, plus the paging metadata a view needs.

    ``rows`` is the current page slice; ``total`` is the match count *before*
    slicing (so the view can show "N markets" and build a pager). ``page`` is
    clamped into ``[1, total_pages]`` so an out-of-range ``?page=`` is safe.
    """

    rows: tuple[Row, ...]
    total: int
    page: int
    page_size: int
    total_pages: int
    sort_key: str
    sort_dir: str

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def build_rows(markets: tuple, tickers: dict) -> tuple[Row, ...]:
    """Flatten ``feed.markets()`` + a ``{symbol: Ticker}`` snapshot into rows.

    A market with no ticker snapshot is skipped (defensive — the context
    provider always supplies one). ``volume`` is derived as notional
    ``price * ticker.volume_24h``.
    """
    rows: list[Row] = []
    for m in markets:
        t = tickers.get(m.symbol)
        if t is None:
            continue
        rows.append(
            Row(
                symbol=m.symbol,
                name=m.display_name,
                base=m.base,
                price=t.price,
                change_pct=t.change_pct_24h,
                volume=t.price * t.volume_24h,
                sector=sector_for(m.base),
            )
        )
    return tuple(rows)


_SORT_ATTR: dict[str, str] = {
    "symbol": "symbol",
    "name": "name",
    "price": "price",
    "change": "change_pct",
    "volume": "volume",
}


def _in_range(value: float, bounds: tuple[float | None, float | None] | None) -> bool:
    """True when ``value`` is within an optional ``(min, max)`` band.

    Either bound may be ``None`` (unbounded on that side); a ``None`` band is no
    filter at all. Bounds are inclusive.
    """
    if bounds is None:
        return True
    lo, hi = bounds
    if lo is not None and value < lo:
        return False
    return not (hi is not None and value > hi)


def query_catalog(
    rows: tuple[Row, ...],
    *,
    q: str = "",
    sector: str = "",
    price_range: tuple[float | None, float | None] | None = None,
    change_band: tuple[float | None, float | None] | None = None,
    vol_range: tuple[float | None, float | None] | None = None,
    sort_key: str = DEFAULT_SORT,
    sort_dir: str = DEFAULT_DIR,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> QueryResult:
    """Filter -> stable-sort -> slice ``rows`` into one :class:`QueryResult` page.

    * **Filter** — substring ``q`` (via :func:`search.matches` over symbol /
      name / base), exact ``sector`` (empty = all), and inclusive numeric bands
      for price / change_pct / volume.
    * **Sort** — by ``sort_key`` (clamped to :data:`SORT_KEYS`) then by symbol
      ascending as a stable tiebreaker, so the order is a deterministic total
      order in both directions. ``sort_dir`` ``"desc"`` reverses only the
      primary key.
    * **Slice** — 1-based ``page`` of ``page_size``; ``page`` is clamped into
      ``[1, total_pages]`` so an out-of-range request returns the last page
      rather than an empty slice.
    """
    key = sort_key if sort_key in _SORT_ATTR else DEFAULT_SORT
    descending = sort_dir.lower() != "asc"

    filtered = [
        r
        for r in rows
        if matches(q, r.symbol, r.name, r.base)
        and (not sector or r.sector == sector)
        and _in_range(r.price, price_range)
        and _in_range(r.change_pct, change_band)
        and _in_range(r.volume, vol_range)
    ]

    # Stable total order: sort by symbol first (always ascending), then a stable
    # sort by the chosen key. Python's sort is stable, so primary-key ties keep
    # the symbol-ascending order regardless of ``sort_dir``.
    attr = _SORT_ATTR[key]
    filtered.sort(key=lambda r: r.symbol)
    filtered.sort(key=lambda r: getattr(r, attr), reverse=descending)

    total = len(filtered)
    size = max(1, page_size)
    total_pages = max(1, -(-total // size))  # ceil
    clamped_page = min(max(1, page), total_pages)
    start = (clamped_page - 1) * size
    page_rows = tuple(filtered[start : start + size])

    return QueryResult(
        rows=page_rows,
        total=total,
        page=clamped_page,
        page_size=size,
        total_pages=total_pages,
        sort_key=key,
        sort_dir="desc" if descending else "asc",
    )
