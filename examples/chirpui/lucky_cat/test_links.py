"""Deterministic link-integrity crawl for the Lucky Cat shell (TASK 3a).

The two-tier rail (navigation.py) emits a fixed set of inner-rail hrefs per
room: ``/portfolio/orders``, ``/portfolio/history``, ``/trade/convert``,
``/activity/deposits``, ``/activity/trades``, ``/settings/security``,
``/settings/display``. Before the sub-pages landed, every one of those links
404'd — the rail advertised destinations that did not exist. The unit
``TestNavModel`` proved the *model* emitted the hrefs but never proved the
*server* could serve them; ``test_room_stubs_render_full_page`` only hit the
five room roots. This is the gap that let seven dead links ship.

This crawl closes it the durable way: render a set of seed pages through the
production-path ``chirp.testing.TestClient`` (no browser, fully in-process,
deterministic), extract every same-origin ``href`` from the rendered HTML
(stripping ``#fragments`` and external/``mailto:``/``tel:`` links), GET each
one, and assert ``status == 200``. Any link the shell renders but cannot serve
fails this test — which is precisely what would have caught the seven 404s.

It is always-on (no browser, no opt-in) so the example's own ``pytest`` run
covers link integrity going forward.
"""

import re

import pytest

from chirp.testing import TestClient
from tests.helpers.auth import login

# Account rooms (/portfolio, /trade, /activity, /settings + their inner-rail
# sub-pages) are now ``@login_required`` — an anonymous crawl gets 302s to
# ``/login`` and never reaches the linked pages, making the link-integrity proof
# vacuous. So the crawl signs in as the demo trader and threads the authenticated
# session cookie through every GET, exactly as a logged-in user navigating the
# shell would. The demo creds + per-app session cookie name come from app.py.
_SESSION_COOKIE = "chirp_session_lucky_cat"


def _auth_headers(cookie: str | None) -> dict[str, str]:
    """Cookie header for an authenticated GET (empty when not signed in)."""
    return {"Cookie": f"{_SESSION_COOKIE}={cookie}"} if cookie else {}


# Seed pages: one per room (so every room's inner rail is exercised) plus a
# market-detail route (whose "this market" lane links to #fragments + sibling
# markets). BTC-MEOW is a guaranteed SimFeed market (feed._MARKET_DEFS).
_SEED_PAGES: tuple[str, ...] = (
    "/",
    "/markets",
    "/markets/trending",
    "/markets/research",
    "/markets/favorites",
    "/portfolio",
    "/trade",
    "/activity",
    "/settings",
    "/markets/BTC-MEOW",
)

# href="..." (single or double quoted). We only care about the value.
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# SSE / streaming routes are intentionally not full-page GETs — they are
# sse-connect-only (registered ``referenced=True``). The shell never renders an
# ``href`` to them, but guard anyway so a future template change can't drag the
# crawl onto a never-terminating stream.
_SKIP_SUFFIXES: tuple[str, ...] = ("/stream",)


def _same_origin_paths(html: str) -> set[str]:
    """Every crawlable same-origin path in ``html``.

    Strips ``#fragments`` (same-page anchors), and drops external schemes
    (``http(s)://``, ``mailto:``, ``tel:``, ``javascript:``), the bare ``#``
    placeholder, and non-page assets (``/static/...``) + SSE streams.
    """
    paths: set[str] = set()
    for raw in _HREF_RE.findall(html):
        href = raw.strip()
        if not href or href.startswith("#"):
            continue
        # External / non-navigational schemes.
        lower = href.lower()
        if lower.startswith(("http://", "https://", "mailto:", "tel:", "javascript:", "data:")):
            continue
        if not href.startswith("/"):
            # Relative links would be ambiguous here; the shell only emits
            # absolute paths. Skip anything that isn't root-anchored.
            continue
        # Strip the #fragment and any query string — we crawl the route, not the
        # in-page anchor or filter state.
        path = href.split("#", 1)[0].split("?", 1)[0]
        if not path:
            continue
        if path.startswith("/static/"):
            continue
        if any(path.endswith(suffix) for suffix in _SKIP_SUFFIXES):
            continue
        paths.add(path)
    return paths


class TestLinkIntegrity:
    """Every same-origin link the shell renders must resolve to a 200."""

    async def test_seed_pages_themselves_resolve(self, example_app) -> None:
        """Sanity floor: every seed page renders before we trust its links."""
        async with TestClient(example_app) as client:
            cookie = await login(
                client, username="neko", password="luckycat", cookie_name=_SESSION_COOKIE
            )
            headers = _auth_headers(cookie)
            for path in _SEED_PAGES:
                response = await client.get(path, headers=headers)
                assert response.status == 200, f"seed page {path} -> {response.status}"

    async def test_no_dead_links_from_seed_pages(self, example_app) -> None:
        """Crawl: collect every same-origin href across the seed pages and GET
        each one. A link the rail advertises but the server cannot serve (the
        seven-404 regression) fails here with the offending path + status."""
        async with TestClient(example_app) as client:
            cookie = await login(
                client, username="neko", password="luckycat", cookie_name=_SESSION_COOKIE
            )
            headers = _auth_headers(cookie)
            discovered: set[str] = set()
            for path in _SEED_PAGES:
                response = await client.get(path, headers=headers)
                assert response.status == 200, f"seed page {path} -> {response.status}"
                discovered |= _same_origin_paths(response.text)

            # The crawl must actually find links (guards against a regex/markup
            # change silently emptying the set and making this test vacuous).
            assert discovered, "no same-origin links discovered — crawl is vacuous"

            broken: dict[str, int] = {}
            for path in sorted(discovered):
                response = await client.get(path, headers=headers)
                if response.status != 200:
                    broken[path] = response.status

            assert not broken, f"dead links (path -> status): {broken}"

    async def test_every_inner_rail_subpage_is_covered(self, example_app) -> None:
        """Belt-and-suspenders: the seven previously-dead sub-pages must appear in
        the discovered link set (proving the crawl exercises *these* routes, not
        just that it found *some* working links)."""
        previously_dead = {
            "/portfolio/orders",
            "/portfolio/history",
            "/trade/convert",
            "/activity/deposits",
            "/activity/trades",
            "/settings/security",
            "/settings/display",
        }
        async with TestClient(example_app) as client:
            cookie = await login(
                client, username="neko", password="luckycat", cookie_name=_SESSION_COOKIE
            )
            headers = _auth_headers(cookie)
            discovered: set[str] = set()
            for path in _SEED_PAGES:
                response = await client.get(path, headers=headers)
                discovered |= _same_origin_paths(response.text)
        missing = previously_dead - discovered
        assert not missing, f"inner-rail links not rendered by the shell: {missing}"


if __name__ == "__main__":  # pragma: no cover - convenience runner
    raise SystemExit(pytest.main([__file__, "-q"]))
