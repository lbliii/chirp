"""Tests for the Trending destination — /markets/trending (#279, PR5).

The third fixed Markets destination: a leaderboard of the catalog's movers across
three segments (Gainers / Losers / Volume), backed by ``ranking.py`` over
``research.build_rows`` (the PR4 query seam). The segmented control swaps a
``#movers-region`` via htmx; snapshot-per-swap, no live re-rank.

Imports are **in-body** (not top-of-module) for the same reason as
``test_query.py`` / ``test_feed_determinism.py``: the autouse
``_lucky_cat_on_path`` fixture only puts the example dir on ``sys.path`` during
test *execution*, not at collection time. Scoped + fast (watchdog-safe).

Coverage:
  * the filesystem router resolves ``markets/trending`` as a STATIC child (not
    captured by the sibling ``{symbol}`` dynamic segment) — ``app.check()`` stays
    clean and the page renders its OWN trending content, not a coin detail;
  * the full page (browser nav) is 200 with the segmented control + leaderboard;
  * each segment swap (htmx, ``HX-Target: movers-region``) returns the
    ``#movers-region`` wrapper with the requested segment pressed;
  * FOOTGUN #2 — each segment toggle self-overrides the inherited boosted outlet
    (``hx-target`` / ``hx-select`` = ``#movers-region``), or the swap lands empty;
  * the rendered order matches ``ranking.py`` for every segment.
"""

import re

import pytest

from chirp.testing import TestClient

pytestmark = pytest.mark.issue(279)

# The htmx headers a segment-toggle click sends: HX-Request + HX-Target pinned to
# the self-overridden #movers-region id (the page.py handler routes the fragment
# off HX-Target).
_SWAP_HEADERS = {"HX-Request": "true", "HX-Target": "movers-region"}


def _rendered_symbols(body: str) -> list[str]:
    """Catalog symbols in table order, read off the per-row coin-detail links."""
    return re.findall(r'href="/markets/([A-Z0-9-]+)"', body)


class TestTrendingContracts:
    """The new route must keep app.check() clean (static-child resolution proof)."""

    def test_app_check_clean(self, example_app) -> None:
        # No SystemExit == 0 ERROR issues (same idiom as
        # TestContracts::test_app_check_passes). A {symbol}-capture collision or an
        # orphan/OOB/htmx footgun would surface here.
        example_app.check()


class TestTrendingPage:
    """Full-page render for browser navigation (GET, no htmx)."""

    async def test_get_full_page_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending")
        assert response.status == 200
        body = response.text
        # The page's own chrome — proves it resolved to MY template, not {symbol}.
        assert "Trending" in body
        assert 'id="movers-region"' in body
        assert "luckycat-chart-toggle" in body
        # No leaked template syntax.
        assert "{{" not in body
        assert "{%" not in body

    async def test_not_treated_as_coin_detail(self, example_app) -> None:
        """`markets/trending` is a STATIC child, not captured by `{symbol}` — so
        it renders the trending leaderboard, NOT the coin-detail hero/order-book
        view that the {symbol} template ships."""
        async with TestClient(example_app) as client:
            trending = await client.get("/markets/trending")
            # A real coin detail (the {symbol} template) for contrast.
            coin = await client.get("/markets/BTC-MEOW")
        assert trending.status == 200
        tbody = trending.text
        # The coin-detail template's signature regions must be ABSENT here.
        assert "luckycat-detail__hero-chart" not in tbody
        assert 'id="order-book"' not in tbody
        # And the coin detail genuinely ships those (so the absence is meaningful).
        assert "luckycat-detail__hero-chart" in coin.text

    async def test_default_segment_is_gainers(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending")
        body = response.text
        # The Gainers toggle is the pressed/active one by default. Bind
        # aria-pressed="true" to the gainers hx-get on the SAME element (no weak
        # fallback) so this fails loudly if any other segment becomes default.
        assert re.search(
            r'aria-pressed="true"[^>]*hx-get="/markets/trending\?seg=gainers"'
            r'|hx-get="/markets/trending\?seg=gainers"[^>]*aria-pressed="true"',
            body,
        )


class TestSegmentSwaps:
    """Each segment swap returns the #movers-region wrapper (htmx fragment)."""

    async def test_each_segment_returns_movers_region(self, example_app) -> None:
        async with TestClient(example_app) as client:
            for seg in ("gainers", "losers", "volume"):
                response = await client.get(f"/markets/trending?seg={seg}", headers=_SWAP_HEADERS)
                assert response.status == 200, seg
                body = response.text
                # The fragment re-emits the SAME wrapper the toggles target.
                assert 'id="movers-region"' in body, seg
                # The requested segment is the pressed one.
                assert 'aria-pressed="true"' in body, seg
                # Fully rendered — no leaked template syntax.
                assert "{{" not in body, seg
                assert "{%" not in body, seg

    async def test_swap_is_fragment_not_full_page(self, example_app) -> None:
        """The segment swap is a bare fragment — the boosted shell's #page-content
        is NOT in the response (it's a fragment, not a page), proving the swap
        won't nest a whole page."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending?seg=volume", headers=_SWAP_HEADERS)
        body = response.text
        assert 'id="page-content"' not in body
        # The shell topbar / rail are absent too — it's just the region.
        assert "chirpui-app-shell__brand" not in body

    async def test_unknown_segment_clamps_to_default(self, example_app) -> None:
        """A tampered/unknown ?seg= clamps to the default (gainers) rather than
        reaching an arbitrary callable."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending?seg=%2Fevil", headers=_SWAP_HEADERS)
        assert response.status == 200
        body = response.text
        assert 'id="movers-region"' in body
        # Gainers (the default) is the pressed segment for an unknown value.
        assert "Gainers" in body


class TestFootgun2:
    """FOOTGUN #2: segment toggles MUST self-override the inherited boosted outlet
    (#main / #page-content) to their OWN #movers-region, or the swap lands empty
    inside the boosted shell."""

    async def test_toggles_self_override_to_movers_region(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending?seg=gainers", headers=_SWAP_HEADERS)
        body = response.text
        # The self-override trio (hx-select is the lever, not hx-disinherit).
        assert 'hx-target="#movers-region"' in body
        assert 'hx-select="#movers-region"' in body
        assert 'hx-swap="outerHTML"' in body
        # The toggles hx-get the segment route per segment.
        assert 'hx-get="/markets/trending?seg=losers"' in body
        assert 'hx-get="/markets/trending?seg=volume"' in body
        # NOT hx-disinherit (the wrong lever — only affects descendants).
        assert "hx-disinherit" not in body

    async def test_full_page_toggles_also_self_override(self, example_app) -> None:
        """The override lives on the toggles in the FULL page too (the first paint
        before any swap), not only in the fragment."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending")
        body = response.text
        assert 'hx-target="#movers-region"' in body
        assert 'hx-select="#movers-region"' in body


class TestOrdering:
    """The rendered leaderboard order matches ranking.py exactly (the single
    source of truth shared with Home / Research)."""

    def _expected(self, ranker, n=10):
        import ranking
        import research
        from feed import get_feed

        feed = get_feed()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        rows = research.build_rows(tuple(markets), tickers)
        fn = getattr(ranking, ranker)
        return [r.symbol for r in fn(rows, n)]

    async def test_gainers_order_matches_ranking(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending?seg=gainers", headers=_SWAP_HEADERS)
        assert _rendered_symbols(response.text) == self._expected("top_gainers")

    async def test_losers_order_matches_ranking(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending?seg=losers", headers=_SWAP_HEADERS)
        assert _rendered_symbols(response.text) == self._expected("top_losers")

    async def test_volume_order_matches_ranking(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets/trending?seg=volume", headers=_SWAP_HEADERS)
        assert _rendered_symbols(response.text) == self._expected("top_volume")
