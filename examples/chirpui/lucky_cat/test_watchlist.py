"""Tests for the Lucky Cat watchlist feature.

The watchlist is the rail's first FUNCTIONAL filter lane: a thread-safe starred-
markets store (``watchlist.py``), a per-card / detail-header star toggle, the
``/watchlist/toggle`` POST returning OOB star + count twins, a live count badge in
the inner rail, and the ``/watchlist`` starred-only page.

Coverage:
  * the store (toggle/add/remove/contains/count/symbols/reset) — no app needed;
  * GET /watchlist renders the starred-only grid + the polished empty state;
  * POST /watchlist/toggle flips the set and returns BOTH OOB twins (star + count);
  * the rail Watchlist lane renders with the live count;
  * FOOTGUN #1 regression guard: the star <button> is NEVER a descendant of the
    market card <a> (a nested interactive that would hijack navigation);
  * FOOTGUN #2: the toggling star overrides the inherited boosted-shell outlet
    (hx-swap="none" + hx-select of its OWN fragment), so it never churns #main.
"""

import re

import pytest
from store_test_helpers import sole_client_store, warm_authed_store

from chirp.testing import TestClient
from tests.helpers.auth import (
    csrf_post,
    extract_session_cookie,
    login,
)

_SESSION_COOKIE = "chirp_session_lucky_cat"


def _session_cookie(response) -> str | None:
    return extract_session_cookie(response, cookie_name=_SESSION_COOKIE)


async def _login(client) -> str:
    """Sign in as the demo account; return the authenticated session cookie."""
    cookie = await login(client, username="neko", password="luckycat", cookie_name=_SESSION_COOKIE)
    assert cookie is not None
    return cookie


def _cookie_header(cookie: str) -> dict:
    """Build a Cookie header for an authed GET of a gated page."""
    return {"Cookie": f"{_SESSION_COOKIE}={cookie}"}


class TestWatchlistStore:
    """The thread-safe starred-markets store (no app needed)."""

    def setup_method(self) -> None:
        import watchlist

        watchlist.reset()

    def test_seeded_empty(self) -> None:
        import watchlist

        assert watchlist.count() == 0
        assert watchlist.symbols() == frozenset()
        assert watchlist.contains("BTC-MEOW") is False

    def test_toggle_flips_and_returns_new_state(self) -> None:
        import watchlist

        # First toggle stars it (returns True); second unstars it (returns False).
        assert watchlist.toggle("BTC-MEOW") is True
        assert watchlist.contains("BTC-MEOW") is True
        assert watchlist.count() == 1
        assert watchlist.toggle("BTC-MEOW") is False
        assert watchlist.contains("BTC-MEOW") is False
        assert watchlist.count() == 0

    def test_add_and_remove_are_idempotent(self) -> None:
        import watchlist

        assert watchlist.add("ETH-MEOW") is True
        assert watchlist.add("ETH-MEOW") is True  # idempotent — no duplicate
        assert watchlist.count() == 1
        assert watchlist.remove("ETH-MEOW") is False
        assert watchlist.remove("ETH-MEOW") is False  # idempotent — no error
        assert watchlist.count() == 0

    def test_symbols_is_immutable_snapshot(self) -> None:
        import watchlist

        watchlist.add("BTC-MEOW")
        watchlist.add("SOL-MEOW")
        snap = watchlist.symbols()
        assert isinstance(snap, frozenset)
        assert snap == frozenset({"BTC-MEOW", "SOL-MEOW"})
        # Mutating the live set after the snapshot does not change the snapshot.
        watchlist.add("DOGE-MEOW")
        assert "DOGE-MEOW" not in snap

    def test_count_tracks_membership(self) -> None:
        import watchlist

        for sym in ("BTC-MEOW", "ETH-MEOW", "SOL-MEOW"):
            watchlist.add(sym)
        assert watchlist.count() == 3
        watchlist.remove("ETH-MEOW")
        assert watchlist.count() == 2

    def test_reset_clears(self) -> None:
        import watchlist

        watchlist.add("BTC-MEOW")
        watchlist.add("ETH-MEOW")
        assert watchlist.count() == 2
        watchlist.reset()
        assert watchlist.count() == 0
        assert watchlist.symbols() == frozenset()

    def test_concurrent_toggles_never_corrupt_count(self) -> None:
        """Free-threading safety: hammer concurrent toggles from real threads and
        assert the count stays consistent with the membership (never negative,
        never drifting). An even number of toggles per symbol returns to unstarred;
        the store never raises and the count equals len(symbols())."""
        import threading

        import watchlist

        symbols = ["BTC-MEOW", "ETH-MEOW", "SOL-MEOW", "DOGE-MEOW"]

        def worker(sym: str) -> None:
            # 100 toggles per thread → even count → back to the starting state.
            for _ in range(100):
                watchlist.toggle(sym)

        # Two threads per symbol (200 toggles each → even → unstarred at the end).
        threads = [threading.Thread(target=worker, args=(s,)) for s in symbols for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Count is always consistent with the snapshot membership (the lock holds).
        assert watchlist.count() == len(watchlist.symbols())
        assert watchlist.count() >= 0
        # 200 (even) toggles per symbol → every symbol back to unstarred.
        assert watchlist.count() == 0


class TestWatchlistPage:
    """GET /markets/favorites renders the starred-only grid + the empty state.

    Favorites moved from /watchlist → /markets/favorites (#282); the page reuses
    the same market_grid + empty-state markup.
    """

    @pytest.mark.issue(282)
    async def test_empty_shows_polished_empty_state(self, example_app) -> None:
        """With nothing starred (seed state), the polished maneki empty state shows
        — and never asserts data it does not render."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response = await client.get("/markets/favorites", headers=_cookie_header(cookie))
            assert response.status == 200
            assert "<html" in response.text
            assert "No starred markets yet" in response.text
            # The maneki paw accent (polished empty state, not a bare <p>).
            assert "luckycat-empty__paw" in response.text
            # No market cards render when nothing is starred.
            assert "luckycat-market-card-cell" not in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    @pytest.mark.issue(282)
    async def test_old_watchlist_url_redirects_to_favorites(self, example_app) -> None:
        """The starred-markets VIEW moved from /watchlist → /markets/favorites
        (#282), so a stale bookmark / external link to /watchlist must NOT 404 —
        it permanently redirects to the new Favorites destination. 308 (Permanent
        Redirect) preserves the method and tells crawlers the move is for good.
        The mutating /watchlist/toggle POST is unaffected (only the GET page moved).
        """
        async with TestClient(example_app) as client:
            response = await client.get("/watchlist")
        assert response.status == 308, "old /watchlist must permanently redirect, not 404"
        location = next(
            (v for k, v in response.headers if k.lower() == "location"),
            None,
        )
        assert location == "/markets/favorites", location

    async def test_renders_only_starred_markets(self, example_app) -> None:
        """With a subset starred, the grid renders exactly those markets — not the
        full markets list (the headline filter behaviour)."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            _, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "BTC-MEOW"},
            )
            _, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "SOL-MEOW"},
            )
            with sole_client_store():
                assert watchlist.symbols() == frozenset({"BTC-MEOW", "SOL-MEOW"})
            response = await client.get("/markets/favorites", headers=_cookie_header(cookie))
            assert response.status == 200
            html = response.text
            assert 'id="watchlist-grid"' in html
            # Only the GRID is filtered (the shell rail + command palette list every
            # market regardless). Market cards are the ONLY elements that carry
            # .luckycat-market-card-cell, so the grid's contents = those cells. The
            # card href to each market is unique per card; the card's star id keys
            # off the symbol — count cards + assert the per-card star ids.
            card_anchors = re.findall(
                r'<a class="luckycat-market-card[^"]*"\s+href="/markets/([^"]+)">', html
            )
            assert set(card_anchors) == {"BTC-MEOW", "SOL-MEOW"}, card_anchors
            # Exactly two cards in the grid.
            assert html.count("luckycat-market-card-cell") == 2
            # The empty state is gone now that something is starred.
            assert "No starred markets yet" not in html
            assert "{{" not in html
            assert "{%" not in html

    async def test_starred_card_star_is_pressed(self, example_app) -> None:
        """A starred market's card star renders pressed (gold ★, aria-pressed)."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            _, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "BTC-MEOW"},
            )
            with sole_client_store():
                assert watchlist.contains("BTC-MEOW") is True
            response = await client.get("/markets/favorites", headers=_cookie_header(cookie))
            assert response.status == 200
            assert 'id="watchlist-star-BTC-MEOW"' in response.text
            assert 'aria-pressed="true"' in response.text
            assert "is-starred" in response.text


class TestWatchlistToggle:
    """POST /watchlist/toggle flips the set + returns BOTH OOB twins."""

    async def test_toggle_returns_both_oob_twins(self, example_app) -> None:
        """A clean toggle returns the star twin (#watchlist-star-{symbol},
        outerHTML) AND the rail count twin (#watchlist-count, innerHTML), both as
        OOB swaps in one response — and flips the starred state."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "BTC-MEOW"},
            )
            assert response.status == 200
            body = response.text
            # Star twin: outerHTML OOB on the toggling control, now pressed.
            assert 'id="watchlist-star-BTC-MEOW"' in body
            assert 'hx-swap-oob="outerHTML"' in body
            assert 'aria-pressed="true"' in body
            # Count twin: innerHTML OOB on the rail badge, now 1.
            assert 'id="watchlist-count"' in body
            assert 'hx-swap-oob="innerHTML"' in body
            assert ">1<" in body or "1</span>" in body
            # The count twin is NOT double-wrapped (registered wrap=False).
            assert 'id="watchlist_count_swap"' not in body
            assert "{{" not in body
            assert "{%" not in body
            # The store flipped.
            with sole_client_store():
                assert watchlist.contains("BTC-MEOW") is True
                assert watchlist.count() == 1

    async def test_toggle_twice_returns_to_unstarred(self, example_app) -> None:
        """Two toggles of the same symbol star then unstar it; the second response
        shows the unpressed star (☆, aria-pressed=false) and a cleared count."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            first, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "ETH-MEOW"},
            )
            assert first.status == 200
            with sole_client_store():
                assert watchlist.contains("ETH-MEOW") is True

            second, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "ETH-MEOW"},
            )
            assert second.status == 200
            assert 'aria-pressed="false"' in second.text
            with sole_client_store():
                assert watchlist.contains("ETH-MEOW") is False
                assert watchlist.count() == 0

    @pytest.mark.issue(281)
    async def test_toggle_overrides_inherited_outlet(self, example_app) -> None:
        """FOOTGUN #2: the star control must override the inherited boosted-shell
        outlet (hx-target=#main / hx-select=#page-content) with hx-swap="none" +
        hx-select of its OWN fragment id, or the toggle churns #main.

        #281 (PR7): the landing is the curated lobby, so star BTC-MEOW first to put
        its card in the watchlist preview (the macro markup is identical wherever a
        card renders; this exercises the real toggle control's self-override)."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                watchlist.add("BTC-MEOW")
            response = await client.get("/", headers=_cookie_header(cookie))
            html = response.text
            star = re.search(r'<button[^>]*id="watchlist-star-BTC-MEOW"[^>]*>', html)
            assert star is not None, "card star not rendered"
            star_tag = star.group(0)
            assert 'hx-swap="none"' in star_tag
            assert 'hx-select="#watchlist-star-BTC-MEOW"' in star_tag
            # It must NOT inherit/select the page-content outlet.
            assert 'hx-select="#page-content"' not in star_tag
            assert 'hx-post="/watchlist/toggle"' in star_tag

    @pytest.mark.issue(282)
    async def test_unstar_on_favorites_removes_card_live(self, example_app) -> None:
        """Unstarring a market WHILE ON /markets/favorites appends a THIRD OOB twin
        that removes the now-unstarred card cell live (hx-swap-oob="delete" on
        #luckycat-card-{symbol}), so the starred-only grid stays a one-glance view
        rather than leaving a stale ☆ card until reload. (The prune now keys off
        the moved /markets/favorites path, #282.)"""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                watchlist.add("BTC-MEOW")
            response, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "BTC-MEOW"},
                extra_headers={"HX-Current-URL": "http://testserver/markets/favorites"},
            )
            assert response.status == 200
            body = response.text
            # The unstar flipped the store.
            with sole_client_store():
                assert watchlist.contains("BTC-MEOW") is False
            # The card-removal OOB twin is present (delete the card cell).
            assert 'id="luckycat-card-BTC-MEOW"' in body
            assert 'hx-swap-oob="delete"' in body
            # The star + count twins still ship (unpressed star, cleared count).
            assert 'aria-pressed="false"' in body
            assert 'id="watchlist-count"' in body
            assert "{{" not in body
            assert "{%" not in body

    @pytest.mark.issue(282)
    async def test_unstar_off_favorites_keeps_card(self, example_app) -> None:
        """Unstarring from the LANDING (not /markets/favorites) does NOT remove the
        card — the toggle stays reversible in place everywhere except the Favorites
        grid (#282)."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                watchlist.add("ETH-MEOW")
            response, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "ETH-MEOW"},
                extra_headers={"HX-Current-URL": "http://testserver/"},
            )
            assert response.status == 200
            body = response.text
            with sole_client_store():
                assert watchlist.contains("ETH-MEOW") is False
            # No card-removal twin off /watchlist — the card stays reversible.
            assert 'hx-swap-oob="delete"' not in body

    @pytest.mark.issue(282)
    async def test_star_on_favorites_does_not_remove_card(self, example_app) -> None:
        """STARRING (not unstarring) on /markets/favorites never emits a removal
        twin — only the unstar transition prunes the starred-only grid."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "DOGE-MEOW"},
                extra_headers={"HX-Current-URL": "http://testserver/markets/favorites"},
            )
            assert response.status == 200
            with sole_client_store():
                assert watchlist.contains("DOGE-MEOW") is True
            # Starring (result starred=True) never removes a card.
            assert 'hx-swap-oob="delete"' not in response.text

    async def test_toggle_unknown_symbol_is_noop(self, example_app) -> None:
        """A tampered/unknown symbol is a no-op flip — the set never gains a
        non-market, and the response is still a well-formed 200 (never a 500)."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            response, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "NOPE-MEOW"},
            )
            assert response.status == 200
            assert watchlist.contains("NOPE-MEOW") is False
            assert watchlist.count() == 0

    async def test_toggle_requires_csrf(self, example_app) -> None:
        """Without a CSRF token the mutating route is rejected (secure-by-default)."""
        async with TestClient(example_app) as client:
            response = await client.post("/watchlist/toggle", data={"symbol": "BTC-MEOW"})
            assert response.status in (400, 403)


class TestWatchlistStarMarkup:
    """The star control's markup contract — including the FOOTGUN #1 regression
    guard that the star is never nested inside the card <a>."""

    @pytest.mark.issue(281)
    async def test_landing_cards_carry_a_star(self, example_app) -> None:
        """Every lobby card carries a star — component-gated by current_user():
        anonymous gets a "sign in to star" <a href="/login"> (a visible
        affordance, never a swallowed 302), signed-in gets the real toggle
        <button id="watchlist-star-{symbol}">. Both forms are SIBLINGS of the card
        <a href="/markets/{symbol}"> (FOOTGUN #1), never descendants.

        #281 (PR7): the landing is now the curated lobby, NOT the full grid — the
        card-bearing regions are the featured card + the watchlist preview, so the
        signed-in case stars markets to populate the preview (the anonymous case
        renders the featured card). The macro markup is shared, so the contract is
        identical to the old grid; only the number/source of cards changed.
        """
        import watchlist

        async with TestClient(example_app) as client:
            # ANONYMOUS — the star is the sign-in login link, not a toggle button.
            anon = await client.get("/")
            assert anon.status == 200
            anon_html = anon.text
            assert "luckycat-watchlist-star" in anon_html
            assert "luckycat-market-card-cell" in anon_html
            # Anonymous gets the sign-in star (<a href="/login">), NOT the toggle.
            assert "luckycat-watchlist-star--signin" in anon_html
            assert 'id="watchlist-star-' not in anon_html
            # The sign-in star is a SIBLING of the card <a>, never nested inside it.
            anon_anchors = re.findall(
                r'<a class="luckycat-market-card[^"]*"\s+href="/markets/[^"]+">(.*?)</a>',
                anon_html,
                re.S,
            )
            # The lobby always renders the featured card (>= 1).
            assert len(anon_anchors) >= 1, "lobby card anchors not found — crawl is vacuous"
            assert not [a for a in anon_anchors if "luckycat-watchlist-star" in a], (
                "anonymous sign-in star is nested INSIDE a market card <a> (FOOTGUN #1)"
            )

            # SIGNED IN — star markets so the watchlist preview populates, then the
            # star is the real toggle button with the per-card id.
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                watchlist.add("BTC-MEOW")
                watchlist.add("SOL-MEOW")
            authed = await client.get("/", headers=_cookie_header(cookie))
            assert authed.status == 200
            authed_html = authed.text
            assert "luckycat-watchlist-star" in authed_html
            # Each card lives in a relative wrapper holding the card + sibling star.
            assert "luckycat-market-card-cell" in authed_html
            # A starred market shows in the watchlist preview as a real toggle.
            assert 'id="watchlist-star-BTC-MEOW"' in authed_html
            assert "luckycat-watchlist-star--signin" not in authed_html
            # The toggle button is a SIBLING of the card <a>, never nested inside it.
            authed_anchors = re.findall(
                r'<a class="luckycat-market-card[^"]*"\s+href="/markets/[^"]+">(.*?)</a>',
                authed_html,
                re.S,
            )
            assert len(authed_anchors) >= 1, "lobby card anchors not found — crawl is vacuous"
            assert not [a for a in authed_anchors if "luckycat-watchlist-star" in a], (
                "signed-in toggle star is nested INSIDE a market card <a> (FOOTGUN #1)"
            )

    @pytest.mark.issue(281)
    async def test_star_is_not_descendant_of_card_anchor(self, example_app) -> None:
        """FOOTGUN #1 regression guard: a <button> inside the full-card <a> is
        invalid HTML and HIJACKS navigation. The star MUST be a SIBLING of the
        card <a>, not a descendant. Parse every market-card anchor's inner HTML
        and assert no watchlist-star button lives inside it.

        #281 (PR7): the landing is the curated lobby — the featured card always
        renders (>= 1 card anchor), so the invariant is still exercised against
        real cards; only the card count/source changed, not the macro contract."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            anchors = re.findall(
                r'<a class="luckycat-market-card[^"]*"\s+href="/markets/[^"]+">(.*?)</a>',
                html,
                re.S,
            )
            assert len(anchors) >= 1, "lobby card anchors not found — crawl is vacuous"
            offenders = [a for a in anchors if "luckycat-watchlist-star" in a]
            assert not offenders, (
                "watchlist star <button> is nested INSIDE a market card <a> "
                "(FOOTGUN #1 — nested interactive hijacks navigation); "
                "it must be a SIBLING of the card anchor"
            )

    async def test_detail_header_star_is_not_inside_back_link(self, example_app) -> None:
        """The market-detail header also carries a star — also component-gated and
        also a sibling, never nested inside the back-link <a> (the same nested-
        interactive footgun). Anonymous gets the sign-in login link; signed-in gets
        the real toggle button. Both live in the .luckycat-detail__star slot, a
        sibling of the back <a>."""
        async with TestClient(example_app) as client:
            # ANONYMOUS — the detail star is the sign-in login link.
            anon = await client.get("/markets/BTC-MEOW")
            assert anon.status == 200
            anon_html = anon.text
            assert "luckycat-detail__star" in anon_html
            assert "luckycat-watchlist-star--signin" in anon_html
            assert 'id="watchlist-star-BTC-MEOW"' not in anon_html
            anon_back = re.search(r'<a class="luckycat-detail__back[^>]*>.*?</a>', anon_html, re.S)
            assert anon_back is not None
            assert "luckycat-watchlist-star" not in anon_back.group(0)

            # SIGNED IN — the detail star is the real toggle button.
            cookie = await _login(client)
            authed = await client.get("/markets/BTC-MEOW", headers=_cookie_header(cookie))
            assert authed.status == 200
            authed_html = authed.text
            assert "luckycat-detail__star" in authed_html
            assert 'id="watchlist-star-BTC-MEOW"' in authed_html
            assert "luckycat-watchlist-star--signin" not in authed_html
            authed_back = re.search(
                r'<a class="luckycat-detail__back[^>]*>.*?</a>', authed_html, re.S
            )
            assert authed_back is not None
            assert "luckycat-watchlist-star" not in authed_back.group(0)


class TestWatchlistRailLane:
    """The rail's Favorites destination renders with the live count badge."""

    @pytest.mark.issue(282)
    async def test_rail_renders_favorites_lane(self, example_app) -> None:
        """The Markets-room inner rail carries a Favorites destination linking to
        the moved /markets/favorites page, with the #watchlist-count OOB target for
        the badge. The other fixed destinations (Home / Trending / Research) ship
        alongside it; the old /watchlist href is gone (#282)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            html = response.text
            # The Favorites destination (a real link to the moved page).
            assert 'href="/markets/favorites"' in html
            assert ">Favorites</span>" in html
            # The old /watchlist href is gone repo-wide.
            assert 'href="/watchlist"' not in html
            # The count OOB target still lives in the rail (fail-loud: a real id),
            # so a star toggle's count twin lands.
            assert 'id="watchlist-count"' in html
            # The fixed destinations replaced the old market list + Filters lane.
            assert 'href="/markets/trending"' in html
            assert 'href="/markets/research"' in html
            assert "All markets" not in html
            assert ">Gainers</span>" not in html
            assert ">Losers</span>" not in html

    async def test_rail_count_reflects_starred(self, example_app) -> None:
        """With markets starred, the rail Watchlist lane shows the count badge."""
        import watchlist

        async with TestClient(example_app) as client:
            cookie = await _login(client)
            await warm_authed_store(client, cookie, cookie_name=_SESSION_COOKIE)
            with sole_client_store():
                watchlist.add("BTC-MEOW")
                watchlist.add("ETH-MEOW")
            response = await client.get("/", headers=_cookie_header(cookie))
            assert response.status == 200
            html = response.text
            # The count badge renders the tally (2) inside the #watchlist-count
            # element.
            count_el = re.search(r'<span id="watchlist-count"[^>]*>(.*?)</span>\s*</a>', html, re.S)
            assert count_el is not None
            assert "luckycat-watchlist-count" in count_el.group(1)
            assert "2" in count_el.group(1)

    async def test_rail_count_empty_when_nothing_starred(self, example_app) -> None:
        """With nothing starred, the badge is empty (no zero pill) but the
        #watchlist-count target still ships (the OOB swap must have a target)."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            html = response.text
            assert 'id="watchlist-count"' in html
            count_el = re.search(r'<span id="watchlist-count"[^>]*>(.*?)</span>\s*</a>', html, re.S)
            assert count_el is not None
            # No badge pill when the watchlist is empty.
            assert "luckycat-watchlist-count" not in count_el.group(1)

    @pytest.mark.issue(282)
    async def test_count_badge_oob_updates_after_toggle_and_favorites_resolves(
        self, example_app
    ) -> None:
        """Acceptance (#282): after the /watchlist → /markets/favorites MOVE, a star
        toggle's live count badge OOB still updates (the detached-badge regression
        the move risked), AND the moved Favorites page resolves and renders the
        starred card. Proves the count twin + the page were not decoupled by the
        move."""
        async with TestClient(example_app) as client:
            cookie = await _login(client)
            # The rail badge starts empty (nothing starred).
            rail = await client.get("/", headers=_cookie_header(cookie))
            assert 'id="watchlist-count"' in rail.text

            # Toggle a star — the count twin must come back with the new tally.
            toggle, cookie = await csrf_post(
                client,
                "/watchlist/toggle",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"symbol": "BTC-MEOW"},
            )
            assert toggle.status == 200
            # The live count badge OOB twin updated (#watchlist-count, innerHTML, 1).
            assert 'id="watchlist-count"' in toggle.text
            assert 'hx-swap-oob="innerHTML"' in toggle.text
            assert ">1<" in toggle.text or "1</span>" in toggle.text

            # The moved Favorites page resolves and renders the starred card.
            favorites = await client.get("/markets/favorites", headers=_cookie_header(cookie))
            assert favorites.status == 200
            assert 'id="watchlist-star-BTC-MEOW"' in favorites.text
            assert "No starred markets yet" not in favorites.text
