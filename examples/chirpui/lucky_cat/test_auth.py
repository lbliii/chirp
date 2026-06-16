"""Auth tests for the lucky_cat example (#275, child of the #220 Lucky Cat epic).

Lucky Cat is **public-browse / gated-trading** (see ``users.py`` / DESIGN.md §7):
the markets grid and a market's detail page are open to anyone, but the account
surfaces (trade, portfolio, watchlist, activity, settings) and every mutation
(deposit, place/cancel order, convert, toggle a star, mark notifications read)
require the signed-in demo trader. The topbar chrome (the $MEOW balance, the
notifications bell, the Deposit action) is conditional on ``current_user()``.

This module is the dedicated auth proof, sitting alongside the per-feature
coverage in ``test_app.py``. It locks down the THREE gating levels and the
sign-in / sign-out flow end to end against the real wired stack (Session → Auth →
CSRF → SecurityHeaders), through the public ``TestClient`` and the verified
``tests.helpers.auth`` login/CSRF helpers (both the CSRF token AND the session
cookie rotate per response, so the helpers pair them):

* **Public browse** — the open routes return 200 with no session.
* **Full-page gating** — anonymous GET of a gated room redirects 302 to
  ``/login?next=<url-encoded path>``; a signed-in GET renders 200.
* **Component gating** — the conditional topbar/star chrome flips between the
  anonymous "Sign in" affordance and the signed-in account chrome.
* **Login flow** — bad creds re-render the form (422, username preserved); good
  creds return an ``HX-Redirect`` to the (safe) ``next`` target and rotate the
  session cookie (anti-fixation regeneration).
* **Action gating + CSRF** — a mutating route is authed AND CSRF-protected.
* **Logout** — clears the session, ``HX-Redirect`` home, and re-gates the rooms.

The demo account is a single shared in-memory user (``neko`` / ``luckycat``,
prefilled on the login page). Tests are deterministic and offline (no sleeps,
no real network); ``conftest.py`` resets every store — including ``users`` —
between tests.
"""

import pytest

from chirp.testing import TestClient, assert_hx_redirect
from tests.helpers.auth import (
    csrf_post,
    extract_csrf_token,
    extract_session_cookie,
    login,
)

_SESSION_COOKIE = "chirp_session_lucky_cat"
_USERNAME = "neko"
_PASSWORD = "luckycat"  # demo-only credential, shown prefilled on the login page

# The full-page-gated rooms: each anonymous GET → 302 /login?next=<encoded path>.
# (One leaf per room family is enough for the redirect contract; signed-in GET of
# each proves the gate opens once authed.)
_GATED_PATHS = (
    "/trade",
    "/portfolio",
    "/portfolio/orders",
    "/activity",
    # Favorites is gated (moved from /watchlist → /markets/favorites, #282); the
    # gate moved with the page, so the anon-redirect contract still holds.
    "/markets/favorites",
    "/settings",
)


def _location(response) -> str | None:
    """The Location header of a redirect (case-insensitive, multi-pair headers)."""
    for hname, hvalue in response.headers:
        if hname.lower() == "location":
            return hvalue
    return None


async def _signed_in_cookie(client) -> str:
    """Log in the demo trader; assert and return the authenticated cookie."""
    cookie = await login(
        client,
        username=_USERNAME,
        password=_PASSWORD,
        cookie_name=_SESSION_COOKIE,
    )
    assert cookie, "login did not yield an authenticated session cookie"
    return cookie


class TestPublicBrowse:
    """Public-browse: the open surfaces serve 200 with no session at all."""

    @pytest.mark.issue(275)
    async def test_public_routes_serve_200_anonymous(self, example_app) -> None:
        """The markets grid, a market detail page, search, login, and the
        healthcheck are all reachable WITHOUT signing in."""
        async with TestClient(example_app) as client:
            for path in (
                "/",
                "/markets/BTC-MEOW",
                "/search?q=btc",
                "/login",
                "/health",
            ):
                response = await client.get(path)
                assert response.status == 200, path

    @pytest.mark.issue(275)
    async def test_market_detail_subroutes_are_public(self, example_app) -> None:
        """The detail page's data sub-routes (/chart + /stream) are public too —
        an anonymous visitor gets the live trading view, not a redirect."""
        async with TestClient(example_app) as client:
            chart = await client.get(
                "/markets/BTC-MEOW/chart?tf=1H", headers={"HX-Request": "true"}
            )
            assert chart.status == 200
            stream = await client.sse("/markets/BTC-MEOW/stream", max_events=2)
            assert stream.status == 200
            assert stream.headers.get("content-type") == "text/event-stream"


class TestFullPageGating:
    """Full-page gating: anonymous GET of a gated room → 302 /login?next=<path>;
    a signed-in GET of the same room → 200."""

    @pytest.mark.issue(275)
    async def test_anonymous_gated_get_redirects_to_login(self, example_app) -> None:
        """Each gated room redirects an anonymous visitor to the login page with a
        URL-encoded ``next`` hop back to where they were headed."""
        from urllib.parse import quote

        async with TestClient(example_app) as client:
            for path in _GATED_PATHS:
                response = await client.get(path)
                assert response.status == 302, path
                expected = f"/login?next={quote(path, safe='')}"
                assert _location(response) == expected, (path, _location(response))

    @pytest.mark.issue(275)
    async def test_next_param_is_url_encoded(self, example_app) -> None:
        """The ``next`` value is URL-encoded (the slash becomes ``%2F``), so the
        redirect target round-trips a nested path safely."""
        async with TestClient(example_app) as client:
            response = await client.get("/portfolio")
            assert response.status == 302
            assert _location(response) == "/login?next=%2Fportfolio"
            orders = await client.get("/portfolio/orders")
            assert _location(orders) == "/login?next=%2Fportfolio%2Forders"

    @pytest.mark.issue(275)
    async def test_signed_in_gated_get_serves_200(self, example_app) -> None:
        """Once authenticated, every gated room renders its full page (the gate
        opens — same cookie, no redirect)."""
        async with TestClient(example_app) as client:
            cookie = await _signed_in_cookie(client)
            for path in _GATED_PATHS:
                response = await client.get(path, headers={"Cookie": f"{_SESSION_COOKIE}={cookie}"})
                assert response.status == 200, path
                assert "<html" in response.text, path


class TestComponentGating:
    """Component gating: the conditional topbar + star chrome flips on
    ``current_user()`` — both branches render on the PUBLIC landing page."""

    @pytest.mark.issue(275)
    async def test_anonymous_landing_shows_signin_not_account_chrome(self, example_app) -> None:
        """An anonymous visitor sees a "Sign in" affordance and NONE of the
        signed-in account chrome (no bell, no Deposit action)."""
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
            # The anonymous identity affordance — a plain link to /login.
            assert "luckycat-signin" in html
            assert 'href="/login"' in html
            # The signed-in-only account chrome is absent.
            assert 'id="notif-bell"' not in html
            assert 'data-action="deposit"' not in html
            # The signed-in user chip / sign-out form is not present.
            assert 'action="/logout"' not in html

    @pytest.mark.issue(275)
    async def test_anonymous_watchlist_star_is_a_login_link(self, example_app) -> None:
        """On a public card the watchlist star is the anonymous login-link form
        (``--signin``), NOT the authenticated toggle button."""
        async with TestClient(example_app) as client:
            html = (await client.get("/")).text
            assert "luckycat-watchlist-star--signin" in html
            # No authenticated toggle button id for any market.
            assert 'id="watchlist-star-' not in html

    @pytest.mark.issue(275)
    async def test_signed_in_landing_shows_account_chrome(self, example_app) -> None:
        """A signed-in visitor sees the full account chrome: the notifications
        bell, the Deposit action, the user name, a Sign-out form, and the live
        toggle star button on cards."""
        async with TestClient(example_app) as client:
            cookie = await _signed_in_cookie(client)
            html = (await client.get("/", headers={"Cookie": f"{_SESSION_COOKIE}={cookie}"})).text
            # Account chrome the anonymous page omits.
            assert 'id="notif-bell"' in html
            assert 'data-action="deposit"' in html
            # Identity: the user chip name + a Sign-out form posting to /logout.
            assert "Demo Trader" in html
            assert 'action="/logout"' in html
            # The star is now the real toggle button, not the login link.
            assert 'id="watchlist-star-' in html
            assert "luckycat-watchlist-star--signin" not in html


class TestLoginFlow:
    """The sign-in page + POST: render, bad-creds 422 re-render, good-creds
    HX-Redirect with a regenerated session."""

    @pytest.mark.issue(275)
    async def test_login_page_renders_prefilled_form(self, example_app) -> None:
        """GET /login renders the sign-in card with the prefilled demo creds and
        no leaked raw template tags."""
        async with TestClient(example_app) as client:
            response = await client.get("/login")
            assert response.status == 200
            html = response.text
            assert 'id="login-form"' in html
            # Prefilled demo credentials keep the live demo one-click.
            assert f'value="{_USERNAME}"' in html
            assert _PASSWORD in html
            # Fully rendered — no leaked template syntax.
            assert "{%" not in html
            assert "{{" not in html

    @pytest.mark.issue(275)
    async def test_bad_credentials_rerender_form_422(self, example_app) -> None:
        """Wrong password → 422 re-rendering ONLY the login_form block, with the
        error message shown and the submitted username preserved (password
        cleared). This is the ValidationError return-type-as-intent pattern."""
        async with TestClient(example_app) as client:
            page = await client.get("/login")
            csrf = extract_csrf_token(page.text)
            cookie = extract_session_cookie(page, cookie_name=_SESSION_COOKIE)
            assert csrf is not None
            headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}
            if cookie:
                headers["Cookie"] = f"{_SESSION_COOKIE}={cookie}"
            response = await client.post(
                "/login",
                data={"username": _USERNAME, "password": "wrong-password", "next": "/"},
                headers=headers,
            )
            assert response.status == 422
            html = response.text
            # The form re-renders (a fragment, not a full-page <html> shell).
            assert 'id="login-form"' in html
            assert "<html" not in html
            # The mismatch error message shows (the apostrophe is HTML-escaped,
            # so match the substrings either side of it).
            assert "That username and password" in html
            assert "match. Try again." in html
            assert 'role="alert"' in html
            # The submitted username is preserved on the re-render.
            assert f'value="{_USERNAME}"' in html
            assert "{%" not in html
            assert "{{" not in html

    @pytest.mark.issue(275)
    async def test_good_credentials_hx_redirect_and_regenerated_session(self, example_app) -> None:
        """Correct creds → an HX-Redirect to the next target (a FULL page reload so
        the persistent topbar repaints its auth state) and a regenerated session
        cookie (anti-fixation: the post-login cookie differs from the pre-login
        one)."""
        async with TestClient(example_app) as client:
            page = await client.get("/login")
            csrf = extract_csrf_token(page.text)
            pre_cookie = extract_session_cookie(page, cookie_name=_SESSION_COOKIE)
            assert csrf is not None
            headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}
            if pre_cookie:
                headers["Cookie"] = f"{_SESSION_COOKIE}={pre_cookie}"
            response = await client.post(
                "/login",
                data={"username": _USERNAME, "password": _PASSWORD, "next": "/"},
                headers=headers,
            )
            # HX-Redirect (not a body) drives the full reload to the next target.
            assert_hx_redirect(response, "/")
            # The session was regenerated (anti-fixation): the cookie rotated.
            post_cookie = extract_session_cookie(response, cookie_name=_SESSION_COOKIE)
            assert post_cookie is not None
            assert post_cookie != pre_cookie


class TestNextRoundTrip:
    """The ?next= round-trip: a gated redirect captures where the user was
    headed, and a successful sign-in returns them there."""

    @pytest.mark.issue(275)
    async def test_gated_redirect_then_login_returns_to_next(self, example_app) -> None:
        """Anonymous GET /portfolio → 302 ?next=%2Fportfolio; a successful login
        carrying that next → HX-Redirect "/portfolio"."""
        async with TestClient(example_app) as client:
            gated = await client.get("/portfolio")
            assert gated.status == 302
            assert _location(gated) == "/login?next=%2Fportfolio"
            # Sign in honouring the captured next hop.
            cookie = await login(
                client,
                username=_USERNAME,
                password=_PASSWORD,
                cookie_name=_SESSION_COOKIE,
                next_url="/portfolio",
            )
            assert cookie
            # Re-run the login POST so we can assert the redirect target itself.
            page = await client.get("/login?next=%2Fportfolio")
            csrf = extract_csrf_token(page.text)
            pre = extract_session_cookie(page, cookie_name=_SESSION_COOKIE)
            headers = (
                {"X-CSRF-Token": csrf, "HX-Request": "true"} if csrf else {"HX-Request": "true"}
            )
            if pre:
                headers["Cookie"] = f"{_SESSION_COOKIE}={pre}"
            response = await client.post(
                "/login",
                data={"username": _USERNAME, "password": _PASSWORD, "next": "/portfolio"},
                headers=headers,
            )
            assert_hx_redirect(response, "/portfolio")


class TestActionGating:
    """Action gating + CSRF: a mutating route requires BOTH a signed-in session
    and a CSRF token (secure-by-default)."""

    @pytest.mark.issue(275)
    async def test_signed_in_deposit_with_csrf_succeeds(self, example_app) -> None:
        """A signed-in deposit with a paired CSRF token returns the empty 204 (the
        visible balance update fans over the live signal, not the body)."""
        async with TestClient(example_app) as client:
            cookie = await _signed_in_cookie(client)
            response, _ = await csrf_post(
                client,
                "/deposit",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={"amount": "250"},
            )
            assert response.status == 204
            assert response.text == ""

    @pytest.mark.issue(275)
    async def test_signed_in_deposit_without_csrf_is_rejected(self, example_app) -> None:
        """A signed-in POST with NO CSRF token is rejected — auth alone does not
        bypass CSRF (the secure stack enforces both)."""
        async with TestClient(example_app) as client:
            cookie = await _signed_in_cookie(client)
            response = await client.post(
                "/deposit",
                data={"amount": "100"},
                headers={"Cookie": f"{_SESSION_COOKIE}={cookie}"},
            )
            assert response.status == 403

    @pytest.mark.issue(275)
    async def test_anonymous_deposit_is_not_a_successful_mutation(self, example_app) -> None:
        """An anonymous POST /deposit (no cookie, no CSRF) never succeeds: it is
        rejected (403) or redirected to login (302) — never the 204 a real credit
        returns."""
        async with TestClient(example_app) as client:
            response = await client.post("/deposit", data={"amount": "100"})
            assert response.status in (302, 403)
            assert response.status != 204


class TestLogout:
    """Logout clears the session, HX-Redirects home, and re-gates the rooms."""

    @pytest.mark.issue(275)
    async def test_logout_redirects_home_and_re_gates(self, example_app) -> None:
        """Signed in → POST /logout (CSRF-paired) returns HX-Redirect "/"; after
        logout, GET /portfolio is gated again (302 back to login) — the session
        truly cleared."""
        async with TestClient(example_app) as client:
            cookie = await _signed_in_cookie(client)
            # While signed in, the gated room is open.
            ok = await client.get("/portfolio", headers={"Cookie": f"{_SESSION_COOKIE}={cookie}"})
            assert ok.status == 200
            # Sign out (a real mutation: CSRF-protected).
            response, post_cookie = await csrf_post(
                client,
                "/logout",
                cookie=cookie,
                cookie_name=_SESSION_COOKIE,
                data={},
            )
            assert_hx_redirect(response, "/")
            # After logout the room re-gates: a GET with the post-logout cookie
            # (or none) is anonymous → 302 back to login.
            headers = {"Cookie": f"{_SESSION_COOKIE}={post_cookie}"} if post_cookie else {}
            gated = await client.get("/portfolio", headers=headers)
            assert gated.status == 302
            assert _location(gated) == "/login?next=%2Fportfolio"
