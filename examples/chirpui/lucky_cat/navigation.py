"""Server-side route-context navigation model for the Lucky Cat shell (#231).

Ported (stripped of the forum domain) from the elbysodic forum's proven
two-tier rail model on the same chirp-ui 0.9.0. Pure Python, frozen dataclasses,
no I/O — the layout calls :func:`route_state` + :func:`shell_navigation` to drive
BOTH a persistent outer **icon rail** (the trading "rooms") and an inner
**contextual rail** whose sections change with where you are.

The crown jewel is :class:`RouteState`: a frozen, queryless view of the current
path with path-prefix ``*_active`` properties. ``shell_navigation`` dispatches on
``route_state.active_room`` to assemble typed :class:`NavSection` / :class:`NavItem`
trees, pruning empty sections so the inner rail never shows a bare header.

Active-state is computed once on the server here and consumed by both rails
(``aria-current="page"`` + the active class). It must stay consistent with the
app-shell layout's client ``syncNav()`` (path-prefix highlight on history events),
which uses the same ``path == href or path.startswith(href + "/")`` rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

# The fixed Markets destinations that live ONE level under ``/markets`` but are
# NOT coins. ``market_detail_active`` excludes these before its depth check so a
# reserved view (``/markets/favorites`` etc.) never pins a coin section in the
# rail. Keep in lock-step with the static children under ``pages/markets/`` and
# the fixed rail destinations in :func:`_markets_sections`.
RESERVED_MARKET_SEGMENTS: frozenset[str] = frozenset({"favorites", "trending", "research"})


def _path_in(path: str, prefix: str) -> bool:
    """True when ``path`` is ``prefix`` or a descendant of it.

    The canonical prefix-match (mirrors chirp-ui ``match="prefix"`` and the
    app-shell layout's ``syncNav()``) so server and client active-state agree.
    """
    return path == prefix or path.startswith(prefix + "/")


def active_route_path(current_path: object) -> str:
    """Return the queryless, fragmentless route path for active-state checks.

    Lifted verbatim from elbysodic: tolerates ``None``, absolute URLs, query
    strings, and fragments, always returning a leading-slash path (``"/"`` for
    empty input).
    """
    raw = str(current_path or "/")
    path = urlsplit(raw).path if "://" in raw else raw.split("?", 1)[0].split("#", 1)[0]
    return path or "/"


@dataclass(frozen=True, slots=True)
class NavItem:
    """A single navigable entry on either rail.

    ``icon`` is a chirp-ui icon *name* (fed to the ``| icon`` filter), NOT an SVG
    sprite id — Lucky Cat ships no sprite sheet. ``badge`` renders a small pill
    (e.g. a signed 24h change like ``"+2.3%"``); ``count`` is a numeric tally.
    """

    key: str
    label: str
    href: str
    active: bool = False
    icon: str | None = None
    badge: str | int | None = None
    count: int | None = None


@dataclass(frozen=True, slots=True)
class NavSection:
    """A labelled group of inner-rail items. ``label=None`` renders no header."""

    key: str
    label: str | None
    items: tuple[NavItem, ...]


@dataclass(frozen=True, slots=True)
class ShellNavigation:
    """The fully-resolved two-tier rail for one request.

    ``primary_items`` is the persistent outer icon rail (same rooms everywhere);
    ``sidebar_sections`` is the inner contextual rail (changes per room), already
    pruned of empty sections.
    """

    active_room: str
    primary_items: tuple[NavItem, ...]
    sidebar_sections: tuple[NavSection, ...]


@dataclass(frozen=True, slots=True)
class RouteState:
    """A queryless snapshot of the current path with active-state properties.

    Build via :func:`route_state`; ``path`` is always the normalized
    :func:`active_route_path` output.
    """

    path: str

    # -- room membership (path-prefix) --------------------------------------

    @property
    def markets_active(self) -> bool:
        """Markets is home — the bare ``/`` and the whole ``/markets`` tree."""
        return self.path == "/" or _path_in(self.path, "/markets")

    @property
    def market_detail_active(self) -> bool:
        """A specific market view: ``/markets/{symbol}`` (one level deep).

        CRITICAL footgun guard: the fixed Markets destinations
        (``/markets/{favorites,trending,research}``) are ALSO one level deep
        under ``/markets``, so a naive "any one-level segment is a coin" check
        would WRONGLY pin them as a coin in the rail. The reserved segments are
        excluded BEFORE the depth check, so only a genuine ``/markets/{symbol}``
        (a coin) reads as a detail route.
        """
        if not self.path.startswith("/markets/"):
            return False
        rest = self.path.removeprefix("/markets/")
        segment = rest.strip("/")
        if "/" in segment:
            return False
        return bool(segment) and segment not in RESERVED_MARKET_SEGMENTS

    @property
    def favorites_active(self) -> bool:
        """The Favorites view — the moved-from-``/watchlist`` starred-markets page."""
        return _path_in(self.path, "/markets/favorites")

    @property
    def portfolio_active(self) -> bool:
        return _path_in(self.path, "/portfolio")

    @property
    def trade_active(self) -> bool:
        return _path_in(self.path, "/trade")

    @property
    def activity_active(self) -> bool:
        return _path_in(self.path, "/activity")

    @property
    def settings_active(self) -> bool:
        return _path_in(self.path, "/settings")

    @property
    def active_room(self) -> str:
        """The icon-rail room this path belongs to. Markets is the default/home.

        ``/markets/favorites`` (and the whole ``/markets`` tree) is a
        Markets-room destination, so it keeps the Markets icon active and shows
        the fixed Markets rail with the Favorites destination lit.
        """
        if self.portfolio_active:
            return "portfolio"
        if self.trade_active:
            return "trade"
        if self.activity_active:
            return "activity"
        if self.settings_active:
            return "settings"
        return "markets"

    @property
    def current_symbol(self) -> str:
        """The market symbol on a detail route, else ``""``."""
        if not self.market_detail_active:
            return ""
        return self.path.removeprefix("/markets/").split("/", 1)[0]


def route_state(current_path: object) -> RouteState:
    """Build a :class:`RouteState` from a raw request path."""
    return RouteState(path=active_route_path(current_path))


# ---------------------------------------------------------------------------
# Primary (icon-rail) rooms — persistent across every route. The rail renders a
# bespoke inline SVG per room via the `rail_svg_icon` macro (keyed on `key`); the
# `icon` name here is the chirp-ui `| icon` glyph FALLBACK for any key without a
# custom SVG (verified to resolve: grid/user/refresh/list/settings).
# ---------------------------------------------------------------------------

_PRIMARY_ROOMS: tuple[tuple[str, str, str, str], ...] = (
    # (key, label, href, icon)
    ("markets", "Markets", "/", "grid"),
    ("portfolio", "Portfolio", "/portfolio", "user"),
    ("trade", "Trade", "/trade", "refresh"),
    ("activity", "Activity", "/activity", "list"),
    ("settings", "Settings", "/settings", "settings"),
)


def _primary_items(state: RouteState) -> tuple[NavItem, ...]:
    active_room = state.active_room
    return tuple(
        NavItem(key=key, label=label, href=href, icon=icon, active=active_room == key)
        for key, label, href, icon in _PRIMARY_ROOMS
    )


def _signed_pct(value: object) -> str:
    """Format a 24h change as a signed percentage pill (e.g. ``"+2.3%"``)."""
    try:
        pct = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return ""
    # Round in the formatter so an unrounded feed value can't produce a noisy badge.
    return f"{pct:+.2f}%"


def _markets_sections(
    state: RouteState,
    markets: tuple,
    tickers: dict | None,
    symbol: str,
    watchlist_count: int = 0,
) -> list[NavSection]:
    # FIXED Markets destinations — "where you are within Markets" — NOT an
    # O(N) one-row-per-market list (that did not scale past a handful of coins;
    # the full catalog now lives ONLY in Research, filtered/sorted/sliced
    # server-side). Four stable lanes:
    #   * Home      → /                  (the curated markets landing)
    #   * Favorites → /markets/favorites (the starred-only view; moved here from
    #                 the old /watchlist). It keeps the live #watchlist-count OOB
    #                 badge so a star toggle on any page still updates the tally.
    #   * Trending  → /markets/trending  (#279 gainers/losers/volume)
    #   * Research  → /markets/research  (#280 the full power surface)
    # The Favorites lane keeps the `nav:favorites` key the sidebar special-cases
    # to host the #watchlist-count OOB target (count value rides NavItem.count).
    return [
        NavSection(
            key="markets",
            label="Markets",
            items=(
                NavItem(
                    key="nav:home",
                    label="Home",
                    href="/",
                    active=state.path == "/",
                    icon="grid",
                ),
                NavItem(
                    key="nav:favorites",
                    label="Favorites",
                    href="/markets/favorites",
                    active=state.favorites_active,
                    icon="star",
                    count=watchlist_count if watchlist_count > 0 else None,
                ),
                NavItem(
                    key="nav:trending",
                    label="Trending",
                    href="/markets/trending",
                    active=_path_in(state.path, "/markets/trending"),
                    # `chart` (▤) is a REGISTERED chirp-ui glyph — an unregistered
                    # name (e.g. "trending-up") passes through the `| icon` filter
                    # verbatim and renders as literal garbage text in the rail.
                    icon="chart",
                ),
                NavItem(
                    key="nav:research",
                    label="Research",
                    href="/markets/research",
                    active=_path_in(state.path, "/markets/research"),
                    icon="search",
                ),
            ),
        )
    ]


def _market_detail_sections(
    state: RouteState,
    markets: tuple,
    tickers: dict | None,
    symbol: str,
    watchlist_count: int = 0,
) -> list[NavSection]:
    # PIN the current coin at the top of the rail (a single active lane), then
    # the fixed Markets destinations below it. The dead #order-book / #trade-tape
    # / #info jump anchors are GONE: they jumped to sections already in view (no
    # value, and they would have to respect the boosted-shell outlet contract to
    # not nest the shell). The signed-24h-change badge keeps the pinned coin
    # informative.
    tickers = tickers or {}
    label = next((m.display_name for m in markets if m.symbol == symbol), symbol)
    pinned = NavSection(
        key="this-market",
        label="Viewing",
        items=(
            NavItem(
                key=f"mkt:{symbol}",
                label=label,
                href=f"/markets/{symbol}",
                active=True,
                badge=_signed_pct(getattr(tickers.get(symbol), "change_pct_24h", None)) or None,
            ),
        ),
    )
    return [pinned, *_markets_sections(state, markets, tickers, symbol, watchlist_count)]


def _portfolio_sections(state: RouteState) -> list[NavSection]:
    p = state.path
    return [
        NavSection(
            key="portfolio",
            label="Portfolio",
            items=(
                NavItem(
                    key="pf:holdings", label="Holdings", href="/portfolio", active=p == "/portfolio"
                ),
                NavItem(
                    key="pf:orders",
                    label="Open orders",
                    href="/portfolio/orders",
                    active=_path_in(p, "/portfolio/orders"),
                ),
                NavItem(
                    key="pf:history",
                    label="History",
                    href="/portfolio/history",
                    active=_path_in(p, "/portfolio/history"),
                ),
            ),
        )
    ]


def _trade_sections(state: RouteState) -> list[NavSection]:
    p = state.path
    return [
        NavSection(
            key="trade",
            label="Trade",
            items=(
                NavItem(key="tr:spot", label="Spot", href="/trade", active=p == "/trade"),
                NavItem(
                    key="tr:convert",
                    label="Convert",
                    href="/trade/convert",
                    active=_path_in(p, "/trade/convert"),
                ),
            ),
        )
    ]


def _activity_sections(state: RouteState) -> list[NavSection]:
    p = state.path
    return [
        NavSection(
            key="activity",
            label="Activity",
            items=(
                NavItem(key="ac:all", label="All", href="/activity", active=p == "/activity"),
                NavItem(
                    key="ac:deposits",
                    label="Deposits",
                    href="/activity/deposits",
                    active=_path_in(p, "/activity/deposits"),
                ),
                NavItem(
                    key="ac:trades",
                    label="Trades",
                    href="/activity/trades",
                    active=_path_in(p, "/activity/trades"),
                ),
            ),
        )
    ]


def _settings_sections(state: RouteState) -> list[NavSection]:
    p = state.path
    return [
        NavSection(
            key="settings",
            label="Settings",
            items=(
                NavItem(
                    key="st:profile", label="Profile", href="/settings", active=p == "/settings"
                ),
                NavItem(
                    key="st:security",
                    label="Security",
                    href="/settings/security",
                    active=_path_in(p, "/settings/security"),
                ),
                NavItem(
                    key="st:display",
                    label="Display",
                    href="/settings/display",
                    active=_path_in(p, "/settings/display"),
                ),
            ),
        )
    ]


def shell_navigation(
    state: RouteState,
    *,
    markets: tuple = (),
    tickers: dict | None = None,
    symbol: str = "",
    watchlist_count: int = 0,
) -> ShellNavigation:
    """Assemble the two-tier rail for ``state``.

    The outer icon rail (``primary_items``) is room-agnostic; the inner rail
    (``sidebar_sections``) dispatches on ``state.active_room`` (with a
    market-detail special case). Empty sections are pruned so the inner rail
    never renders a bare header. ``watchlist_count`` drives the Watchlist filter
    lane's live count badge in the Markets room.
    """
    symbol = symbol or state.current_symbol
    room = state.active_room

    if room == "markets" and state.market_detail_active:
        sections = _market_detail_sections(state, markets, tickers, symbol, watchlist_count)
    elif room == "markets":
        sections = _markets_sections(state, markets, tickers, symbol, watchlist_count)
    elif room == "portfolio":
        sections = _portfolio_sections(state)
    elif room == "trade":
        sections = _trade_sections(state)
    elif room == "activity":
        sections = _activity_sections(state)
    elif room == "settings":
        sections = _settings_sections(state)
    else:  # pragma: no cover - active_room is exhaustive
        sections = _markets_sections(state, markets, tickers, symbol)

    return ShellNavigation(
        active_room=room,
        primary_items=_primary_items(state),
        sidebar_sections=tuple(s for s in sections if s.items),
    )
