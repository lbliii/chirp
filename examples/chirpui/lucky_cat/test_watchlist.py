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

from chirp.testing import TestClient
from tests.helpers.auth import extract_csrf_token, extract_session_cookie

_SESSION_COOKIE = "chirp_session_lucky_cat"


def _session_cookie(response) -> str | None:
    return extract_session_cookie(response, cookie_name=_SESSION_COOKIE)


async def _csrf_headers(client, *, htmx: bool = True) -> dict:
    page = await client.get("/")
    cookie = _session_cookie(page)
    csrf = extract_csrf_token(page.text)
    assert csrf is not None
    headers = {"X-CSRF-Token": csrf}
    if htmx:
        headers["HX-Request"] = "true"
    if cookie:
        headers["Cookie"] = f"{_SESSION_COOKIE}={cookie}"
    return headers


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
    """GET /watchlist renders the starred-only grid + the empty state."""

    async def test_empty_shows_polished_empty_state(self, example_app) -> None:
        """With nothing starred (seed state), the polished maneki empty state shows
        — and never asserts data it does not render."""
        async with TestClient(example_app) as client:
            response = await client.get("/watchlist")
            assert response.status == 200
            assert "<html" in response.text
            assert "No starred markets yet" in response.text
            # The maneki paw accent (polished empty state, not a bare <p>).
            assert "luckycat-empty__paw" in response.text
            # No market cards render when nothing is starred.
            assert "luckycat-market-card-cell" not in response.text
            assert "{{" not in response.text
            assert "{%" not in response.text

    async def test_renders_only_starred_markets(self, example_app) -> None:
        """With a subset starred, the grid renders exactly those markets — not the
        full markets list (the headline filter behaviour)."""
        import watchlist

        watchlist.add("BTC-MEOW")
        watchlist.add("SOL-MEOW")
        async with TestClient(example_app) as client:
            response = await client.get("/watchlist")
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

        watchlist.add("BTC-MEOW")
        async with TestClient(example_app) as client:
            response = await client.get("/watchlist")
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
            headers = await _csrf_headers(client)
            response = await client.post(
                "/watchlist/toggle", data={"symbol": "BTC-MEOW"}, headers=headers
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
            assert watchlist.contains("BTC-MEOW") is True
            assert watchlist.count() == 1

    async def test_toggle_twice_returns_to_unstarred(self, example_app) -> None:
        """Two toggles of the same symbol star then unstar it; the second response
        shows the unpressed star (☆, aria-pressed=false) and a cleared count."""
        import watchlist

        async with TestClient(example_app) as client:
            headers = await _csrf_headers(client)
            first = await client.post(
                "/watchlist/toggle", data={"symbol": "ETH-MEOW"}, headers=headers
            )
            assert first.status == 200
            assert watchlist.contains("ETH-MEOW") is True

            second = await client.post(
                "/watchlist/toggle", data={"symbol": "ETH-MEOW"}, headers=headers
            )
            assert second.status == 200
            assert 'aria-pressed="false"' in second.text
            assert watchlist.contains("ETH-MEOW") is False
            assert watchlist.count() == 0

    async def test_toggle_overrides_inherited_outlet(self, example_app) -> None:
        """FOOTGUN #2: the star control must override the inherited boosted-shell
        outlet (hx-target=#main / hx-select=#page-content) with hx-swap="none" +
        hx-select of its OWN fragment id, or the toggle churns #main."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            star = re.search(r'<button[^>]*id="watchlist-star-BTC-MEOW"[^>]*>', html)
            assert star is not None, "card star not rendered"
            star_tag = star.group(0)
            assert 'hx-swap="none"' in star_tag
            assert 'hx-select="#watchlist-star-BTC-MEOW"' in star_tag
            # It must NOT inherit/select the page-content outlet.
            assert 'hx-select="#page-content"' not in star_tag
            assert 'hx-post="/watchlist/toggle"' in star_tag

    async def test_unstar_on_watchlist_removes_card_live(self, example_app) -> None:
        """Unstarring a market WHILE ON /watchlist appends a THIRD OOB twin that
        removes the now-unstarred card cell live (hx-swap-oob="delete" on
        #luckycat-card-{symbol}), so the starred-only grid stays a one-glance view
        rather than leaving a stale ☆ card until reload."""
        import watchlist

        watchlist.add("BTC-MEOW")
        async with TestClient(example_app) as client:
            headers = await _csrf_headers(client)
            headers["HX-Current-URL"] = "http://testserver/watchlist"
            response = await client.post(
                "/watchlist/toggle", data={"symbol": "BTC-MEOW"}, headers=headers
            )
            assert response.status == 200
            body = response.text
            # The unstar flipped the store.
            assert watchlist.contains("BTC-MEOW") is False
            # The card-removal OOB twin is present (delete the card cell).
            assert 'id="luckycat-card-BTC-MEOW"' in body
            assert 'hx-swap-oob="delete"' in body
            # The star + count twins still ship (unpressed star, cleared count).
            assert 'aria-pressed="false"' in body
            assert 'id="watchlist-count"' in body
            assert "{{" not in body
            assert "{%" not in body

    async def test_unstar_off_watchlist_keeps_card(self, example_app) -> None:
        """Unstarring from the LANDING (not /watchlist) does NOT remove the card —
        the toggle stays reversible in place everywhere except /watchlist."""
        import watchlist

        watchlist.add("ETH-MEOW")
        async with TestClient(example_app) as client:
            headers = await _csrf_headers(client)
            headers["HX-Current-URL"] = "http://testserver/"
            response = await client.post(
                "/watchlist/toggle", data={"symbol": "ETH-MEOW"}, headers=headers
            )
            assert response.status == 200
            body = response.text
            assert watchlist.contains("ETH-MEOW") is False
            # No card-removal twin off /watchlist — the card stays reversible.
            assert 'hx-swap-oob="delete"' not in body

    async def test_star_on_watchlist_does_not_remove_card(self, example_app) -> None:
        """STARRING (not unstarring) on /watchlist never emits a removal twin —
        only the unstar transition prunes the starred-only grid."""
        import watchlist

        async with TestClient(example_app) as client:
            headers = await _csrf_headers(client)
            headers["HX-Current-URL"] = "http://testserver/watchlist"
            response = await client.post(
                "/watchlist/toggle", data={"symbol": "DOGE-MEOW"}, headers=headers
            )
            assert response.status == 200
            assert watchlist.contains("DOGE-MEOW") is True
            # Starring (result starred=True) never removes a card.
            assert 'hx-swap-oob="delete"' not in response.text

    async def test_toggle_unknown_symbol_is_noop(self, example_app) -> None:
        """A tampered/unknown symbol is a no-op flip — the set never gains a
        non-market, and the response is still a well-formed 200 (never a 500)."""
        import watchlist

        async with TestClient(example_app) as client:
            headers = await _csrf_headers(client)
            response = await client.post(
                "/watchlist/toggle", data={"symbol": "NOPE-MEOW"}, headers=headers
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

    async def test_landing_cards_carry_a_star(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            html = response.text
            assert "luckycat-watchlist-star" in html
            # Each card lives in a relative wrapper holding the card + sibling star.
            assert "luckycat-market-card-cell" in html
            assert 'id="watchlist-star-BTC-MEOW"' in html

    async def test_star_is_not_descendant_of_card_anchor(self, example_app) -> None:
        """FOOTGUN #1 regression guard: a <button> inside the full-card <a> is
        invalid HTML and HIJACKS navigation. The star MUST be a SIBLING of the
        card <a>, not a descendant. Parse every market-card anchor's inner HTML
        and assert no watchlist-star button lives inside it."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            html = response.text
            anchors = re.findall(
                r'<a class="luckycat-market-card[^"]*"\s+href="/markets/[^"]+">(.*?)</a>',
                html,
                re.S,
            )
            assert len(anchors) >= 4, "market card anchors not found — crawl is vacuous"
            offenders = [a for a in anchors if "luckycat-watchlist-star" in a]
            assert not offenders, (
                "watchlist star <button> is nested INSIDE a market card <a> "
                "(FOOTGUN #1 — nested interactive hijacks navigation); "
                "it must be a SIBLING of the card anchor"
            )

    async def test_detail_header_star_is_not_inside_back_link(self, example_app) -> None:
        """The market-detail header also carries a star — also a sibling, never
        nested inside the back-link <a> (the same nested-interactive footgun)."""
        async with TestClient(example_app) as client:
            response = await client.get("/markets/BTC-MEOW")
            assert response.status == 200
            html = response.text
            assert "luckycat-detail__star" in html
            assert 'id="watchlist-star-BTC-MEOW"' in html
            back = re.search(r'<a class="luckycat-detail__back[^>]*>.*?</a>', html, re.S)
            assert back is not None
            assert "luckycat-watchlist-star" not in back.group(0)


class TestWatchlistRailLane:
    """The rail's Watchlist filter lane renders with the live count badge."""

    async def test_rail_renders_watchlist_lane(self, example_app) -> None:
        """The Markets-room inner rail carries a Watchlist lane linking to the real
        /watchlist page, with the #watchlist-count OOB target for the badge."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            html = response.text
            # The functional Watchlist lane (a real link, not a cosmetic filter).
            assert 'href="/watchlist"' in html
            assert ">Watchlist</span>" in html
            # The count OOB target lives in the rail (fail-loud: a real id).
            assert 'id="watchlist-count"' in html
            # The "All markets" lane (returns to the landing) still ships below it.
            # The old cosmetic Gainers/Losers no-op lanes were removed — the rail
            # must never advertise a dead-end /#gainers anchor.
            assert "All markets" in html
            assert ">Gainers</span>" not in html
            assert ">Losers</span>" not in html

    async def test_rail_count_reflects_starred(self, example_app) -> None:
        """With markets starred, the rail Watchlist lane shows the count badge."""
        import watchlist

        watchlist.add("BTC-MEOW")
        watchlist.add("ETH-MEOW")
        async with TestClient(example_app) as client:
            response = await client.get("/")
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
