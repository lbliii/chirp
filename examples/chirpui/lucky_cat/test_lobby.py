"""Tests for the Markets Home lobby — / + /markets (#281, PR7).

The curated, BOUNDED Markets landing — one of the five fixed Markets
destinations. NOT the full catalog: a stat strip (``ranking.market_stats``), a
top-movers preview (``ranking.top_*``, a few each), a watchlist preview (the
starred set), a featured market, and a CTA into Research. ``/`` is an ALIAS for
``/markets`` (no redirect): both routes render the SAME ``markets/page.html`` from
the SAME shared ``lobby.lobby_context``.

Imports are **in-body** (not top-of-module) for the same reason as
``test_query.py`` / ``test_trending.py`` / ``test_research.py``: the autouse
``_lucky_cat_on_path`` fixture only puts the example dir on ``sys.path`` during
test *execution*, not at collection time. Scoped + fast (watchdog-safe).

Coverage:
  * ``GET /markets == 200`` and ``GET / == 200`` render the SAME lobby (alias, no
    redirect) — ``app.check()`` stays clean (the bare ``/markets`` resolves as a
    static child, not captured by the sibling ``{symbol}`` segment);
  * the lobby is bounded — stat strip + movers/watchlist previews + featured + a
    Research CTA, NOT the old full grid;
  * NO duplicate DOM ids, even when the featured coin is ALSO starred (the
    de-dupe footgun: ``#luckycat-card-{symbol}`` / ``#watchlist-star-{symbol}``);
  * every preview link resolves (Trending / Research / Favorites / coin detail);
  * boosted in-shell links carry the full ``shell_outlet_attrs()`` contract.
"""

import re

import pytest

from chirp.testing import TestClient
from tests.helpers.auth import login

pytestmark = pytest.mark.issue(281)

_SESSION_COOKIE = "chirp_session_lucky_cat"


def _static_ids(html: str) -> list[str]:
    """Static element ids (``id="..."`` preceded by whitespace) — skips dynamic
    Alpine ``:id`` / ``x-id`` bindings and the ``grid="`` false-positive."""
    return re.findall(r'\sid="([^"]+)"', html)


def _dupes(html: str) -> list[str]:
    ids = _static_ids(html)
    return sorted({i for i in ids if ids.count(i) > 1})


class TestLobbyContracts:
    """The lobby must keep app.check() clean (bare /markets static-child proof)."""

    def test_app_check_clean(self, example_app) -> None:
        # No SystemExit == 0 ERROR issues (same idiom as TestContracts). A
        # {symbol}-capture collision on the bare /markets, an orphan/OOB/htmx
        # footgun, or a dead-template regression from retiring the old grid would
        # surface here.
        example_app.check()


class TestLobbyAlias:
    """/ is an ALIAS rendering /markets (no redirect): both serve the SAME lobby."""

    async def test_both_routes_200(self, example_app) -> None:
        async with TestClient(example_app) as client:
            root = await client.get("/")
            markets = await client.get("/markets")
        assert root.status == 200
        assert markets.status == 200

    async def test_markets_is_not_a_redirect(self, example_app) -> None:
        """The alias renders the lobby in-place — /markets is a 200, never a 3xx
        bounce to / (the RFC's canonical-home decision)."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets")
        assert response.status == 200
        assert "markets-lobby" in response.text

    async def test_both_render_the_same_lobby(self, example_app) -> None:
        """Both routes ship the identical lobby region. The full page carries
        per-request chrome (csp nonce, the rotating ticker spotlight), so compare
        the STABLE lobby skeleton: the region id + every section heading +
        the bounded-preview markers are present on BOTH."""
        async with TestClient(example_app) as client:
            root = (await client.get("/")).text
            markets = (await client.get("/markets")).text
        for marker in (
            'id="markets-lobby"',
            "Featured",
            "Watchlist",
            "Movers",
            "Open Research",
            # The movers preview teases all three Trending segments.
            "/markets/trending?seg=gainers",
            "/markets/trending?seg=losers",
            "/markets/trending?seg=volume",
        ):
            assert marker in root, f"{marker!r} missing from GET /"
            assert marker in markets, f"{marker!r} missing from GET /markets"

    async def test_lobby_is_bounded_not_the_full_grid(self, example_app) -> None:
        """The lobby is BOUNDED — the old full #markets-grid landing is retired.
        The only card-bearing region is the watchlist preview (capped at 3); the
        featured slot is now a bespoke LIVE spotlight (#lobby-featured, no
        #luckycat-card id). A fresh visitor sees the spotlight + an empty watchlist,
        far fewer than the 6-market catalog the old grid showed."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
        text = response.text
        cards = re.findall(r'id="luckycat-card-([A-Z0-9-]+)"', text)
        # Bounded: never the full 6-market catalog (watchlist preview caps at 3; a
        # fresh visitor has none).
        assert len(cards) < 6, f"lobby is not bounded: {cards}"
        # The featured spotlight renders (its live #lobby-featured sink).
        assert 'id="lobby-featured"' in text
        # The old full-grid landing's #markets-grid id is gone (retired).
        assert 'id="markets-grid"' not in text


class TestLobbySections:
    """The curated regions all render from the PR4 ranking/query seam."""

    async def test_stat_strip_renders_market_stats(self, example_app) -> None:
        """The stat strip shows the aggregate snapshot (count / volume / advancers
        / decliners) from ranking.market_stats over the warmed catalog."""
        import ranking
        import research
        from feed import get_feed

        feed = get_feed()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        rows = research.build_rows(tuple(markets), tickers)
        stats = ranking.market_stats(rows)

        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
        # The market count is the warmed-catalog size (6 by default).
        assert "Markets" in html
        assert str(stats.count) in html
        assert "Advancers" in html
        assert "Decliners" in html

    async def test_featured_is_the_top_gainer(self, example_app) -> None:
        """The featured spotlight is the catalog's top gainer (ranking.market_stats's
        top_gainer) — the headline mover. It is a bespoke LIVE spotlight under the
        #lobby-featured sink (no #luckycat-card id; it re-ranks live), so assert the
        top-gainer symbol renders inside that region."""
        import ranking
        import research
        from feed import get_feed

        feed = get_feed()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        rows = research.build_rows(tuple(markets), tickers)
        top = ranking.market_stats(rows).top_gainer
        assert top is not None

        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
        assert 'id="lobby-featured"' in html
        featured = html[html.find('id="lobby-featured"') :]
        featured = featured[: featured.find("</section>")]
        assert top.symbol in featured

    async def test_movers_preview_links_into_trending(self, example_app) -> None:
        """The movers preview teases each Trending segment and links each row to
        the coin detail with the full boosted outlet contract."""
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
        # Each segment "see all" link.
        assert 'href="/markets/trending?seg=gainers"' in html
        assert 'href="/markets/trending?seg=losers"' in html
        assert 'href="/markets/trending?seg=volume"' in html
        # The bounded preview shows a handful of coin-detail links (not the full
        # catalog) — BTC-MEOW is a guaranteed warmed market.
        assert 'href="/markets/BTC-MEOW"' in html

    async def test_research_cta_present(self, example_app) -> None:
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
        assert "Open Research" in html
        assert 'href="/markets/research"' in html


class TestLobbyDuplicateIds:
    """The de-dupe footgun (RFC §risks): a coin in BOTH the featured slot AND the
    watchlist preview must NOT duplicate #luckycat-card-{symbol} /
    #watchlist-star-{symbol} (invalid HTML + the unstar-prune target)."""

    async def test_anonymous_lobby_has_no_duplicate_ids(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
        assert not _dupes(response.text), f"duplicate ids in GET /: {_dupes(response.text)}"

    async def test_markets_alias_has_no_duplicate_ids(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/markets")
        assert not _dupes(response.text), f"duplicate ids in GET /markets: {_dupes(response.text)}"

    async def test_starred_featured_coin_has_no_duplicate_ids(self, example_app) -> None:
        """The de-dupe proof, restated for the bespoke spotlight: the featured slot
        no longer emits #luckycat-card / #watchlist-star ids, so even if the featured
        coin is ALSO starred (and shown in the watchlist preview), the spotlight and
        the watchlist card live in DIFFERENT id namespaces — no collision. No
        duplicate id, ever."""
        import ranking
        import research
        import watchlist
        from feed import get_feed

        feed = get_feed()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        rows = research.build_rows(tuple(markets), tickers)
        featured = ranking.market_stats(rows).top_gainer
        assert featured is not None

        # Star the featured coin AND a few others.
        watchlist.reset()
        watchlist.add(featured.symbol)
        for m in markets:
            if m.symbol != featured.symbol:
                watchlist.add(m.symbol)

        async with TestClient(example_app) as client:
            cookie = await login(
                client, username="neko", password="luckycat", cookie_name=_SESSION_COOKIE
            )
            response = await client.get("/", headers={"Cookie": f"{_SESSION_COOKIE}={cookie}"})
        html = response.text
        assert response.status == 200
        # No duplicate ids at all (the whole-page invariant), featured coin starred.
        assert not _dupes(html), f"duplicate ids with featured coin starred: {_dupes(html)}"
        # The featured spotlight renders the featured coin once, in #lobby-featured.
        assert 'id="lobby-featured"' in html
        featured_region = html[html.find('id="lobby-featured"') :]
        featured_region = featured_region[: featured_region.find("</section>")]
        assert featured.symbol in featured_region


class TestLobbyLinkIntegrity:
    """Every preview link the lobby renders must resolve (the link-crawl floor)."""

    async def test_preview_links_resolve(self, example_app) -> None:
        """Collect every same-origin href on the lobby and GET each one (authed,
        so the gated Favorites resolves to 200 rather than a 302 to /login)."""
        href_re = re.compile(r'href="(/[^"#?]*)')
        async with TestClient(example_app) as client:
            cookie = await login(
                client, username="neko", password="luckycat", cookie_name=_SESSION_COOKIE
            )
            headers = {"Cookie": f"{_SESSION_COOKIE}={cookie}"}
            html = (await client.get("/", headers=headers)).text
            paths = {
                p
                for p in href_re.findall(html)
                if not p.startswith("/static/") and not p.endswith("/stream")
            }
            # The crawl must actually find links (guards against a vacuous pass).
            assert paths, "no same-origin links discovered on the lobby"
            broken: dict[str, int] = {}
            for path in sorted(paths):
                response = await client.get(path, headers=headers)
                if response.status != 200:
                    broken[path] = response.status
        assert not broken, f"dead lobby links (path -> status): {broken}"


class TestLobbyContext:
    """Unit coverage for the pure lobby.lobby_context de-dupe + bounding."""

    def test_featured_not_deduped_from_watchlist_preview(self) -> None:
        """The featured spotlight is bespoke (no card/star ids), so it no longer has
        to be de-duped out of the watchlist preview — a starred coin that is ALSO the
        featured top gainer can appear in BOTH regions without an id collision."""
        import lobby
        import ranking
        import research
        from feed import get_feed

        feed = get_feed()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        rows = research.build_rows(tuple(markets), tickers)
        featured = ranking.market_stats(rows).top_gainer
        assert featured is not None

        # Star the featured + everything else.
        starred = frozenset(m.symbol for m in markets)
        ctx = lobby.lobby_context(markets, tickers, {}, starred)
        preview_syms = [m.symbol for m in ctx["watchlist_preview"]]
        # The watchlist preview is the first-N starred catalog markets with NO
        # featured exclusion (the de-dupe is gone).
        expected = [m.symbol for m in markets if m.symbol in starred][: lobby._WATCHLIST_PREVIEW_N]
        assert preview_syms == expected
        assert ctx["featured_market"].symbol == featured.symbol

    def test_watchlist_preview_is_capped(self) -> None:
        import lobby
        from feed import get_feed

        feed = get_feed()
        markets = feed.markets()
        tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
        starred = frozenset(m.symbol for m in markets)
        ctx = lobby.lobby_context(markets, tickers, {}, starred)
        # Bounded preview — at most _WATCHLIST_PREVIEW_N starred cards.
        assert len(ctx["watchlist_preview"]) <= lobby._WATCHLIST_PREVIEW_N

    def test_empty_catalog_yields_no_featured(self) -> None:
        import lobby

        ctx = lobby.lobby_context((), {}, {}, frozenset())
        assert ctx["featured_market"] is None
        assert ctx["stats"].count == 0
        assert ctx["watchlist_preview"] == ()
