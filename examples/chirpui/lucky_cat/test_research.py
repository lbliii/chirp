"""Tests for the Research destination — /markets/research (#280, PR6).

The fourth fixed Markets destination and the power surface for 500+ coins:
search + facet filters (sector / price / change / volume bands) + sortable
column headers + SERVER-SIDE pagination + a lightweight server-rendered compare.
URL-param-driven (``?q=&sort=&dir=&page=&sector=`` + the band keys + ``cmp``),
backed by ``research.query_catalog`` over ``research.build_rows`` (the PR4 query
seam). Control changes swap a ``#research-results`` region via htmx.

Imports are **in-body** (not top-of-module) for the same reason as
``test_query.py`` / ``test_trending.py``: the autouse ``_lucky_cat_on_path``
fixture only puts the example dir on ``sys.path`` during test *execution*, not at
collection time. Scoped + fast (watchdog-safe).

Coverage:
  * the filesystem router resolves ``markets/research`` as a STATIC child (not
    captured by the sibling ``{symbol}`` dynamic segment) — ``app.check()`` stays
    clean and the page renders its OWN research content, not a coin detail;
  * the full page (browser nav) is 200 with the search box + facets + table;
  * ``?q=`` / ``?sort=`` / ``?page=`` drive deterministic, correctly-sliced
    results matching ``research.query_catalog`` exactly;
  * a control swap (htmx, ``HX-Target: research-results``) returns the
    ``#research-results`` wrapper (and NOT the boosted ``#page-content``);
  * FOOTGUN #2 (CRITICAL) — every search / sort / filter / paginate / compare
    control self-overrides the inherited boosted outlet (``hx-target`` /
    ``hx-select`` = ``#research-results``), or the swap lands empty;
  * the lightweight compare tray pins / unpins via ``?cmp=``;
  * the ``research_url`` querystring helper preserves the active state, resets
    page on a filter change, and keeps page on a pager click.
"""

import re

import pytest

from chirp.testing import TestClient

pytestmark = pytest.mark.issue(280)

# The htmx headers a control click sends: HX-Request + HX-Target pinned to the
# self-overridden #research-results id (the page.py handler routes the fragment
# off HX-Target).
_SWAP_HEADERS = {"HX-Request": "true", "HX-Target": "research-results"}


def _rendered_symbols(body: str) -> list[str]:
    """Catalog symbols in table order, read off the per-row coin-detail links.

    Run this against the FRAGMENT swap (the isolated #research-results region),
    NOT the full page: the boosted shell chrome (the sidebar market list, the
    command palette, the topbar ticker, and — until the PR9 reserved-segment
    guard lands — the inner-rail "this market" anchors that ``market_detail_active``
    wrongly pins for any one-level ``/markets/<x>`` path) also emit
    ``href="/markets/..."`` links, so the full page is not a clean read of the
    table order. The fragment contains only my region. (Trending's TestOrdering
    asserts against the fragment for the identical reason.)
    """
    return re.findall(r'href="/markets/([A-Z0-9-]+)"', body)


def _warmed_rows():
    """Rows built from a locally-constructed warmed SimFeed (never get_feed()),
    per test_feed_determinism.py doctrine — the single source the page reads."""
    from feed import DEFAULT_SEED, SimFeed
    from research import build_rows

    feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
    feed.reset()
    feed.warm()
    markets = feed.markets()
    tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
    return build_rows(markets, tickers)


class TestResearchContracts:
    """The new route must keep app.check() clean (static-child resolution proof)."""

    def test_app_check_clean(self, example_app) -> None:
        # No SystemExit == 0 ERROR issues (same idiom as TestContracts). A
        # {symbol}-capture collision or an orphan/OOB/htmx footgun surfaces here.
        example_app.check()


class TestResearchPage:
    """Full-page render for browser navigation (GET, no htmx)."""

    async def test_get_full_page_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/research")
        assert response.status == 200
        body = response.text
        # The page's own chrome — proves it resolved to MY template, not {symbol}.
        assert "Research" in body
        assert 'id="research-results"' in body
        assert "luckycat-research__search" in body
        # Sortable headers + facets are present.
        assert "luckycat-research__sort" in body
        assert "luckycat-research__facet" in body
        # No leaked template syntax.
        assert "{{" not in body
        assert "{%" not in body

    async def test_not_treated_as_coin_detail(self, example_app) -> None:
        """`markets/research` is a STATIC child, not captured by `{symbol}` — so
        it renders the research surface, NOT the coin-detail hero/order-book view
        that the {symbol} template ships."""
        async with TestClient(example_app) as client:
            research = await client.get("/markets/research")
            coin = await client.get("/markets/BTC-MEOW")
        assert research.status == 200
        body = research.text
        # The coin-detail template's signature regions must be ABSENT here.
        assert "luckycat-detail__hero-chart" not in body
        assert 'id="order-book"' not in body
        # And the coin detail genuinely ships those (so the absence is meaningful).
        assert "luckycat-detail__hero-chart" in coin.text

    async def test_default_lists_full_catalog(self, example_app) -> None:
        """No filters → the region lists the whole (warmed) catalog in the default
        sort order (volume desc), matching query_catalog exactly. Asserted against
        the FRAGMENT (the isolated region) — see _rendered_symbols."""
        from research import query_catalog

        async with TestClient(example_app) as client:
            response = await client.get("/markets/research", headers=_SWAP_HEADERS)
        expected = [r.symbol for r in query_catalog(_warmed_rows()).rows]
        assert _rendered_symbols(response.text) == expected


class TestQueryParams:
    """?q= / ?sort= / ?page= drive deterministic, correctly-sliced results.

    Asserted against the FRAGMENT swap (the isolated #research-results region) so
    the shell chrome's coin links don't pollute the read — see _rendered_symbols.
    """

    async def test_search_filters_to_match(self, example_app) -> None:
        from research import query_catalog

        async with TestClient(example_app) as client:
            response = await client.get("/markets/research?q=btc", headers=_SWAP_HEADERS)
        rendered = _rendered_symbols(response.text)
        expected = [r.symbol for r in query_catalog(_warmed_rows(), q="btc").rows]
        assert rendered == expected
        # The 6-symbol default catalog: "btc" matches exactly BTC-MEOW.
        assert rendered == ["BTC-MEOW"]

    async def test_sort_order_matches_query_catalog(self, example_app) -> None:
        from research import query_catalog

        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/research?sort=price&dir=asc", headers=_SWAP_HEADERS
            )
        expected = [
            r.symbol for r in query_catalog(_warmed_rows(), sort_key="price", sort_dir="asc").rows
        ]
        assert _rendered_symbols(response.text) == expected

    async def test_pagination_slices_correctly(self, example_app) -> None:
        """?page= slices the catalog and an out-of-range page clamps to the last
        page (never an empty slice); each matches query_catalog's slice for that
        page (DEFAULT_PAGE_SIZE=25, so the 6-coin default fits one page)."""
        from research import DEFAULT_PAGE_SIZE, query_catalog

        async with TestClient(example_app) as client:
            page1 = await client.get(
                "/markets/research?sort=symbol&dir=asc&page=1", headers=_SWAP_HEADERS
            )
            page2 = await client.get(
                "/markets/research?sort=symbol&dir=asc&page=2", headers=_SWAP_HEADERS
            )
        rows = _warmed_rows()
        q1 = query_catalog(rows, sort_key="symbol", sort_dir="asc", page=1)
        # The 6-coin default catalog is < one page; page 1 lists all rows.
        assert _rendered_symbols(page1.text) == [r.symbol for r in q1.rows]
        assert len(_rendered_symbols(page1.text)) == min(len(rows), DEFAULT_PAGE_SIZE)
        # An out-of-range ?page= clamps to the last page (never an empty slice).
        assert page2.status == 200
        assert _rendered_symbols(page2.text) == [
            r.symbol for r in query_catalog(rows, sort_key="symbol", sort_dir="asc", page=2).rows
        ]

    async def test_unknown_sort_clamps_to_default(self, example_app) -> None:
        """A tampered ?sort= clamps to the default (volume), proving it never
        reaches an arbitrary Row attribute via the page."""
        from research import query_catalog

        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/research?sort=../../etc/passwd", headers=_SWAP_HEADERS
            )
        expected = [r.symbol for r in query_catalog(_warmed_rows()).rows]
        assert _rendered_symbols(response.text) == expected

    async def test_facet_filter_by_sector(self, example_app) -> None:
        from research import query_catalog

        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/research?sector=Meme&sort=symbol&dir=asc", headers=_SWAP_HEADERS
            )
        expected = [
            r.symbol
            for r in query_catalog(
                _warmed_rows(), sector="Meme", sort_key="symbol", sort_dir="asc"
            ).rows
        ]
        assert _rendered_symbols(response.text) == expected


class TestControlSwaps:
    """A control swap returns the #research-results wrapper (htmx fragment)."""

    async def test_swap_returns_results_region(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/research?q=eth", headers=_SWAP_HEADERS)
        assert response.status == 200
        body = response.text
        # The fragment re-emits the SAME wrapper the controls target.
        assert 'id="research-results"' in body
        # Fully rendered — no leaked template syntax.
        assert "{{" not in body
        assert "{%" not in body

    async def test_swap_is_fragment_not_full_page(self, example_app) -> None:
        """The control swap is a bare fragment — the boosted shell's #page-content
        is NOT in the response, so the swap can't nest a whole page."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/research?sort=price", headers=_SWAP_HEADERS)
        body = response.text
        assert 'id="page-content"' not in body
        # The shell topbar / rail are absent too — it's just the region.
        assert "chirpui-app-shell__brand" not in body


class TestFootgun2:
    """FOOTGUN #2: every control MUST self-override the inherited boosted outlet
    (#main / #page-content) to #research-results, or the swap lands empty inside
    the boosted shell."""

    async def test_controls_self_override_in_fragment(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/research", headers=_SWAP_HEADERS)
        body = response.text
        # The self-override trio (hx-select is the lever, not hx-disinherit).
        assert 'hx-target="#research-results"' in body
        assert 'hx-select="#research-results"' in body
        assert 'hx-swap="outerHTML"' in body
        # NOT hx-disinherit (the wrong lever — only affects descendants).
        assert "hx-disinherit" not in body

    async def test_controls_self_override_in_full_page(self, example_app) -> None:
        """The override lives on the controls in the FULL page too (the first paint
        before any swap), not only in the fragment."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/research")
        body = response.text
        assert 'hx-target="#research-results"' in body
        assert 'hx-select="#research-results"' in body

    async def test_every_control_kind_self_overrides(self, example_app) -> None:
        """Each hx-get CONTROL in the region (search form, facet chips, sort
        headers, pager, compare) carries the self-override. Asserted against the
        FRAGMENT (the isolated region, no shell hx-get controls to dilute the
        count), so every hx-get is matched 1:1 by a #research-results target +
        select."""
        async with TestClient(example_app) as client:
            response = await client.get(
                "/markets/research?cmp=BTC-MEOW&sort=symbol", headers=_SWAP_HEADERS
            )
        body = response.text
        n_hxget = body.count("hx-get=")
        n_target = body.count('hx-target="#research-results"')
        n_select = body.count('hx-select="#research-results"')
        # Many control kinds are present (search + facets + headers + compare).
        assert n_hxget > 5
        # Every hx-get control carries exactly one self-override target + select.
        assert n_target == n_hxget
        assert n_select == n_hxget


class TestCompare:
    """The lightweight server-rendered compare tray (?cmp=)."""

    async def test_pin_renders_compare_tray(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/research?cmp=BTC-MEOW,ETH-MEOW")
        assert response.status == 200
        body = response.text
        assert "luckycat-research__compare" in body
        # Both pinned symbols appear in the compare tray.
        assert "BTC-MEOW" in body
        assert "ETH-MEOW" in body
        # The pinned rows in the main table show "Pinned", not a Compare link.
        assert "is-pinned" in body

    async def test_unknown_compare_symbol_dropped(self, example_app) -> None:
        """A hand-typed unknown ?cmp= symbol is dropped (known-only), so the tray
        only ever pins real catalog coins."""
        async with TestClient(example_app) as client:
            with_unknown = await client.get("/markets/research?cmp=NOPE-MEOW")
        body = with_unknown.text
        # No compare tray when the only requested symbol is unknown.
        assert "luckycat-research__compare-table" not in body

    async def test_no_compare_tray_without_cmp(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/research")
        assert "luckycat-research__compare-table" not in response.text


class TestResearchUrl:
    """Unit tests on the pure research_url querystring helper (param preservation,
    page-reset on filter change, page-keep on a pager click)."""

    def _module(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parent / "pages" / "markets" / "research" / "page.py"
        spec = importlib.util.spec_from_file_location("research_page_under_test", path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_filter_change_resets_page(self) -> None:
        pg = self._module()
        state = {"q": "btc", "sort": "price", "dir": "asc", "page": "3"}
        url = pg.research_url(state, sort="volume", dir="desc")
        assert "page=" not in url
        assert "sort=volume" in url
        assert "dir=desc" in url
        assert "q=btc" in url

    def test_pager_keeps_page(self) -> None:
        pg = self._module()
        state = {"q": "btc", "sort": "price", "dir": "asc"}
        url = pg.research_url(state, page="2")
        assert "page=2" in url

    def test_empty_state_is_clean_path(self) -> None:
        pg = self._module()
        assert pg.research_url({}) == "/markets/research"

    def test_drops_empty_values(self) -> None:
        pg = self._module()
        url = pg.research_url({"q": "", "sector": "Meme", "sort": "", "dir": ""})
        assert url == "/markets/research?sector=Meme"
