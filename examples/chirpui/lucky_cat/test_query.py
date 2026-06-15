"""Tests for the Markets query seam (#277): search / research / ranking.

Pure-Python modules, no app / async / DB needed. Imports are **in-body** (not
top-of-module) because the autouse ``_lucky_cat_on_path`` fixture in
``conftest.py`` only puts the example dir on ``sys.path`` during test *execution*,
not at collection time — the same reason ``test_feed_determinism.py`` imports
in-body. Runs in <1s (watchdog-safe).

Two layers:
  * unit tests on synthetic :class:`research.Row` fixtures (precise control over
    ties, ranges, paging);
  * one integration test that builds rows from the *warmed* SimFeed and pins the
    leaderboard ORDER against the determinism golden in
    ``test_feed_determinism.py`` — so the ranking math and the feed can never
    silently drift apart.
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.issue(277)


def _row(symbol, *, name="", base="", price=1.0, change_pct=0.0, volume=0.0, sector="Other"):
    """A synthetic catalog row (sector defaulted; symbol drives the tiebreak)."""
    from research import Row

    return Row(
        symbol=symbol,
        name=name or symbol,
        base=base or symbol.split("-", 1)[0],
        price=price,
        change_pct=change_pct,
        volume=volume,
        sector=sector,
    )


# ---------------------------------------------------------------------------
# search.matches — the one shared substring matcher (Cmd-K + Research).
# ---------------------------------------------------------------------------


class TestSearchMatches:
    def test_empty_query_matches_everything(self) -> None:
        from search import matches

        assert matches("", "BTC-MEOW", "Bitcoin") is True
        assert matches("   ", "anything") is True

    def test_token_substring_case_insensitive(self) -> None:
        from search import matches

        assert matches("btc", "BTC-MEOW") is True
        assert matches("BITCOIN", "BTC-MEOW", "Bitcoin") is True

    def test_every_token_must_match_some_haystack(self) -> None:
        from search import matches

        # token-AND: both tokens appear in the joined haystack.
        assert matches("bt me", "BTC-MEOW", "Bitcoin") is True
        # "xrp" is absent, so the whole query fails even though "bt" matches.
        assert matches("bt xrp", "BTC-MEOW", "Bitcoin") is False

    def test_no_match(self) -> None:
        from search import matches

        assert matches("doge", "BTC-MEOW", "Bitcoin") is False


# ---------------------------------------------------------------------------
# research.build_rows / sector_for — flattening + sector taxonomy.
# ---------------------------------------------------------------------------


class TestBuildRows:
    def test_notional_volume_and_sector(self) -> None:
        from research import build_rows

        markets = (SimpleNamespace(symbol="BTC-MEOW", display_name="Bitcoin", base="BTC"),)
        tickers = {"BTC-MEOW": SimpleNamespace(price=100.0, change_pct_24h=2.5, volume_24h=3.0)}
        (row,) = build_rows(markets, tickers)
        assert row.symbol == "BTC-MEOW"
        assert row.name == "Bitcoin"
        assert row.price == 100.0
        assert row.change_pct == 2.5
        assert row.volume == 300.0  # notional = price * base volume
        assert row.sector == "Store of Value"

    def test_unknown_base_falls_back_to_other(self) -> None:
        from research import DEFAULT_SECTOR, build_rows

        markets = (SimpleNamespace(symbol="ZZZ-MEOW", display_name="Zed", base="ZZZ"),)
        tickers = {"ZZZ-MEOW": SimpleNamespace(price=1.0, change_pct_24h=0.0, volume_24h=1.0)}
        (row,) = build_rows(markets, tickers)
        assert row.sector == DEFAULT_SECTOR

    def test_market_without_ticker_is_skipped(self) -> None:
        from research import build_rows

        markets = (SimpleNamespace(symbol="GONE-MEOW", display_name="Gone", base="GONE"),)
        assert build_rows(markets, {}) == ()

    def test_sector_for_is_case_insensitive(self) -> None:
        from research import DEFAULT_SECTOR, sector_for

        assert sector_for("eth") == "Smart Contract"
        assert sector_for("UNKNOWN") == DEFAULT_SECTOR


# ---------------------------------------------------------------------------
# research.query_catalog — filter -> stable-sort -> slice.
# ---------------------------------------------------------------------------


class TestQueryCatalog:
    def _rows(self):
        return (
            _row("AAA-MEOW", name="Alpha", price=10.0, change_pct=5.0, volume=300.0, sector="Meme"),
            _row("BBB-MEOW", name="Beta", price=20.0, change_pct=-2.0, volume=100.0, sector="Meme"),
            _row(
                "CCC-MEOW", name="Gamma", price=30.0, change_pct=5.0, volume=200.0, sector="House"
            ),
        )

    def test_filter_by_query(self) -> None:
        from research import query_catalog

        res = query_catalog(self._rows(), q="beta")
        assert [r.symbol for r in res.rows] == ["BBB-MEOW"]
        assert res.total == 1

    def test_filter_by_sector(self) -> None:
        from research import query_catalog

        res = query_catalog(self._rows(), sector="Meme", sort_key="symbol", sort_dir="asc")
        assert [r.symbol for r in res.rows] == ["AAA-MEOW", "BBB-MEOW"]

    def test_filter_by_price_range(self) -> None:
        from research import query_catalog

        res = query_catalog(self._rows(), price_range=(15.0, None), sort_key="symbol")
        assert {r.symbol for r in res.rows} == {"BBB-MEOW", "CCC-MEOW"}

    def test_filter_by_change_band(self) -> None:
        from research import query_catalog

        # Only strictly-down coins: change in [-inf, 0).
        res = query_catalog(self._rows(), change_band=(None, -0.01))
        assert [r.symbol for r in res.rows] == ["BBB-MEOW"]

    def test_filter_by_volume_range(self) -> None:
        from research import query_catalog

        res = query_catalog(self._rows(), vol_range=(150.0, 250.0))
        assert [r.symbol for r in res.rows] == ["CCC-MEOW"]

    def test_stable_tiebreak_both_directions(self) -> None:
        from research import query_catalog

        # AAA and CCC tie at change_pct=5.0; symbol-ascending breaks the tie the
        # SAME way regardless of sort_dir (the secondary key never reverses).
        asc = query_catalog(self._rows(), sort_key="change", sort_dir="asc")
        desc = query_catalog(self._rows(), sort_key="change", sort_dir="desc")
        assert [r.symbol for r in asc.rows] == ["BBB-MEOW", "AAA-MEOW", "CCC-MEOW"]
        assert [r.symbol for r in desc.rows] == ["AAA-MEOW", "CCC-MEOW", "BBB-MEOW"]

    def test_unknown_sort_key_clamps_to_default(self) -> None:
        from research import query_catalog

        res = query_catalog(self._rows(), sort_key="../../etc/passwd")
        assert res.sort_key == "volume"  # DEFAULT_SORT

    def test_pagination_slices_and_reports(self) -> None:
        from research import query_catalog

        rows = tuple(_row(f"{i:02d}-MEOW", volume=float(i)) for i in range(10))
        page1 = query_catalog(rows, sort_key="symbol", sort_dir="asc", page=1, page_size=4)
        assert [r.symbol for r in page1.rows] == ["00-MEOW", "01-MEOW", "02-MEOW", "03-MEOW"]
        assert page1.total == 10
        assert page1.total_pages == 3
        assert page1.has_next is True
        assert page1.has_prev is False

    def test_out_of_range_page_clamps_to_last(self) -> None:
        from research import query_catalog

        rows = tuple(_row(f"{i:02d}-MEOW") for i in range(10))
        res = query_catalog(rows, page=99, page_size=4)
        assert res.page == 3  # clamped to last page, not an empty slice
        assert len(res.rows) == 2
        assert res.has_next is False
        assert res.has_prev is True

    def test_empty_catalog_is_one_empty_page(self) -> None:
        from research import query_catalog

        res = query_catalog(())
        assert res.rows == ()
        assert res.total == 0
        assert res.total_pages == 1
        assert res.page == 1


# ---------------------------------------------------------------------------
# ranking — gainers / losers / volume + market_stats.
# ---------------------------------------------------------------------------


class TestRanking:
    def _rows(self):
        return (
            _row("AAA-MEOW", change_pct=5.0, volume=300.0),
            _row("BBB-MEOW", change_pct=-2.0, volume=100.0),
            _row("CCC-MEOW", change_pct=5.0, volume=200.0),  # ties AAA on change
            _row("DDD-MEOW", change_pct=0.0, volume=400.0),
        )

    def test_top_gainers_orders_desc_with_symbol_tiebreak(self) -> None:
        from ranking import top_gainers

        assert [r.symbol for r in top_gainers(self._rows(), 3)] == [
            "AAA-MEOW",
            "CCC-MEOW",  # tie with AAA on +5.0 -> symbol ascending
            "DDD-MEOW",
        ]

    def test_top_losers_orders_asc(self) -> None:
        from ranking import top_losers

        assert [r.symbol for r in top_losers(self._rows(), 2)] == ["BBB-MEOW", "DDD-MEOW"]

    def test_top_volume_orders_desc(self) -> None:
        from ranking import top_volume

        assert [r.symbol for r in top_volume(self._rows(), 2)] == ["DDD-MEOW", "AAA-MEOW"]

    def test_market_stats(self) -> None:
        from ranking import market_stats

        stats = market_stats(self._rows())
        assert stats.count == 4
        assert stats.total_volume == 1000.0
        assert stats.advancers == 2  # AAA, CCC (strictly > 0)
        assert stats.decliners == 1  # BBB
        assert stats.top_gainer.symbol == "AAA-MEOW"
        assert stats.top_loser.symbol == "BBB-MEOW"

    def test_market_stats_empty_catalog(self) -> None:
        from ranking import market_stats

        stats = market_stats(())
        assert stats.count == 0
        assert stats.total_volume == 0.0
        assert stats.top_gainer is None
        assert stats.top_loser is None


class TestRankingOnWarmedFeed:
    """Integration: build rows from the warmed SimFeed and pin the leaderboard
    ORDER against the determinism golden (``test_feed_determinism.py``). Uses a
    locally-constructed feed (never ``get_feed()``) per that file's doctrine."""

    def _rows(self):
        from feed import DEFAULT_SEED, SimFeed
        from research import build_rows

        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        feed.reset()
        feed.warm()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        return build_rows(markets, tickers)

    def test_gainers_match_golden_change_order(self) -> None:
        from ranking import top_gainers

        # Golden 24h change %: ETH +10.35, BTC +4.6, KOBAN -0.62, DOGE -3.1,
        # PAW -3.54, SOL -11.65.
        assert [r.symbol for r in top_gainers(self._rows(), 6)] == [
            "ETH-MEOW",
            "BTC-MEOW",
            "KOBAN-MEOW",
            "DOGE-MEOW",
            "PAW-MEOW",
            "SOL-MEOW",
        ]

    def test_losers_are_gainers_reversed(self) -> None:
        from ranking import top_losers

        assert [r.symbol for r in top_losers(self._rows(), 6)] == [
            "SOL-MEOW",
            "PAW-MEOW",
            "DOGE-MEOW",
            "KOBAN-MEOW",
            "BTC-MEOW",
            "ETH-MEOW",
        ]

    def test_volume_is_notional_order(self) -> None:
        from ranking import top_volume

        # Notional (price * base volume) ranks BTC top and PAW bottom — the raw
        # base-unit volume on the ticker would (wrongly) put DOGE/PAW on top.
        assert [r.symbol for r in top_volume(self._rows(), 6)] == [
            "BTC-MEOW",
            "SOL-MEOW",
            "ETH-MEOW",
            "KOBAN-MEOW",
            "DOGE-MEOW",
            "PAW-MEOW",
        ]
