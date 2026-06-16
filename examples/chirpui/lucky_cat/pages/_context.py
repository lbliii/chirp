"""Root context for lucky_cat — markets list, house token, shell actions.

CHIRP layer: context providers merge into mounted pages. Markets and tickers come
from the ``FeedSource`` seam (``get_feed()``). The topbar Deposit action uses
``action="deposit"`` so chirp-ui renders ``data-action="deposit"`` and the layout
delegator opens the deposit dialog.

DOMAIN geometry below (``Sparkline``, ``hero_chart``) is market-card SVG math —
skip when learning Chirp; read ``feed.py`` for the data seam instead.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import TypeVar

import notifications
import watchlist
from command_palette import palette_results
from feed import get_feed
from wallet import INITIAL_MEOW, balance

_V = TypeVar("_V")

from chirp import ShellAction, ShellActions, ShellActionZone
from chirp.middleware.auth import current_user

# Sparkline SVG geometry — a fixed 100x36 viewBox stretched to the card with
# preserveAspectRatio="none". y maps high→top(2)/low→bottom(34) with 2px breathing
# room so the stroke is not clipped.
_SPARK_W = 100.0
_SPARK_TOP = 2.0
_SPARK_BOTTOM = 34.0
_SPARK_MID = 18.0


@dataclass(frozen=True, slots=True)
class Sparkline:
    """Precomputed gradient-area sparkline for one market card.

    The geometry is built server-side (no JS chart lib): ``line`` is the SVG
    ``points`` string for a ``<polyline>``, ``area`` closes that path to the
    baseline for the gradient ``<polygon>`` fill, and ``up`` keys the jade/red
    direction off first-vs-last close so the chart agrees with the 24h delta pill.
    ``ok`` is False when there are too few points to draw a shape (the card then
    skips the SVG entirely).
    """

    ok: bool
    up: bool
    line: str
    area: str


def _spark_y(c: float, lo: float, span: float) -> float:
    """Map a close price into the sparkline's y band (high→top, low→bottom)."""
    if span > 0:
        return _SPARK_BOTTOM - (((c - lo) / span) * (_SPARK_BOTTOM - _SPARK_TOP))
    return _SPARK_MID


def _sparkline(closes: tuple[float, ...]) -> Sparkline:
    n = len(closes)
    if n < 2:
        return Sparkline(ok=False, up=True, line="", area="")
    up = closes[-1] >= closes[0]
    lo, hi = min(closes), max(closes)
    span = hi - lo
    pts: list[str] = []
    for i, c in enumerate(closes):
        x = (i * _SPARK_W) / (n - 1)
        y = _spark_y(c, lo, span)
        pts.append(f"{x:.2f},{y:.2f}")
    line = " ".join(pts)
    area = f"0,36 {line} 100,36"
    return Sparkline(ok=True, up=up, line=line, area=area)


@dataclass(frozen=True, slots=True)
class HeroChart:
    """Hero area chart geometry for one timeframe, plus per-point crosshair data.

    Extends the :class:`Sparkline` contract (``ok`` / ``up`` / ``line`` / ``area``
    use the identical 100x36 viewBox geometry, so the jade/red direction and the
    points string never drift from the landing-grid spark) with the data the
    hover crosshair needs: ``points`` is a tuple of ``(x, y, price, label)`` so a
    small vanilla controller can snap a vertical line + price/time tooltip to the
    nearest sample. The whole struct is JSON-safe (floats + strings) so it can be
    emitted into a nonced ``<script type="application/json">`` island — no eval,
    no Alpine dependency.
    """

    ok: bool
    up: bool
    line: str
    area: str
    interval: str
    points: tuple[tuple[float, float, float, str], ...]


def _interval_label(interval: str, index: int, total: int) -> str:
    """Human bucket label for the crosshair tooltip, oldest→newest.

    The synthetic interval series carries a bucket index, not a wall clock, so we
    render a relative "N <unit> ago" label (newest bucket = "now"). Kept tiny and
    dependency-free; purely presentational for the hover tooltip.
    """
    ago = total - 1 - index
    unit = {"1m": "min", "1H": "h", "1D": "d", "1W": "w"}.get(interval, "")
    if ago == 0:
        return "now"
    return f"{ago}{unit} ago"


def hero_chart(closes: tuple[float, ...], interval: str) -> HeroChart:
    """Build the hero area chart geometry + crosshair points for a timeframe.

    Reuses :func:`_sparkline`'s viewBox + direction contract so the focal hero
    chart and the landing-grid spark can never diverge. ``closes`` is oldest→
    newest; ``ok`` is False when there are too few points to draw (the template
    skips the SVG so it never renders an empty/broken chart).
    """
    spark = _sparkline(closes)
    if not spark.ok:
        return HeroChart(ok=False, up=spark.up, line="", area="", interval=interval, points=())
    n = len(closes)
    lo, hi = min(closes), max(closes)
    span = hi - lo
    points: list[tuple[float, float, float, str]] = []
    for i, c in enumerate(closes):
        x = (i * _SPARK_W) / (n - 1)
        y = _spark_y(c, lo, span)
        points.append((round(x, 2), round(y, 2), c, _interval_label(interval, i, n)))
    return HeroChart(
        ok=True,
        up=spark.up,
        line=spark.line,
        area=spark.area,
        interval=interval,
        points=tuple(points),
    )


class _LazySymbolMap(Mapping[str, _V]):
    """A per-symbol map that computes + caches each value on first access.

    ``context()`` used to eagerly build ``tickers`` and ``sparklines`` for EVERY
    market on EVERY request — O(N) work that is fatal at a 500-coin catalog and
    pure waste on non-market routes (the topbar/rail never index by symbol). This
    Mapping defers the per-symbol build to ``__getitem__`` and memoizes it, so a
    template doing ``tickers.get(sym)`` / ``sparklines[sym]`` is unchanged but only
    the symbols actually touched are built; an untouched route pays ~nothing.

    It is a real ``collections.abc.Mapping`` so ``.get(key, default)``,
    ``key in m``, ``len(m)`` and truthiness all behave like the old plain ``dict``
    the templates and ``navigation.py`` (``tickers = tickers or {}``) expect.
    Membership is checked against the known-symbol set WITHOUT triggering a build,
    so ``.get(absent)`` / ``absent in m`` stay free. Request-scoped (one per
    ``context()`` call), so the cache is never shared across threads/requests.
    """

    __slots__ = ("_build", "_cache", "_known", "_symbols")

    def __init__(self, symbols: tuple[str, ...], build: Callable[[str], _V]) -> None:
        # ``_symbols`` preserves catalog order for iteration; ``_known`` is the
        # O(1) membership set so a lookup against a 500-coin catalog stays cheap.
        self._symbols = symbols
        self._known = frozenset(symbols)
        self._build = build
        self._cache: dict[str, _V] = {}

    def __getitem__(self, symbol: str) -> _V:
        if symbol not in self._known:
            raise KeyError(symbol)
        if symbol not in self._cache:
            self._cache[symbol] = self._build(symbol)
        return self._cache[symbol]

    def __contains__(self, symbol: object) -> bool:
        # Cheap O(1) membership — never triggers a build.
        return symbol in self._known

    def __iter__(self) -> Iterator[str]:
        return iter(self._symbols)

    def __len__(self) -> int:
        return len(self._symbols)


def context() -> dict:
    feed = get_feed()
    markets = feed.markets()
    symbols = tuple(m.symbol for m in markets)
    # Per-symbol ticker + sparkline maps, LAZY: each value is computed and cached
    # only when a template indexes that symbol (the grid touches every visible
    # card; the topbar/rail touch none). At a 500-coin catalog this turns an O(N)
    # per-request build into O(rendered cards). Snapshot reads are sync and cheap.
    tickers = _LazySymbolMap(symbols, feed.ticker)
    # Sparkline geometry is built from the closing price of each warmed candle
    # (oldest→newest); the template renders the precomputed SVG points (no JS).
    sparklines = _LazySymbolMap(
        symbols,
        lambda sym: _sparkline(tuple(c.close for c in feed.candles(sym, limit=32))),
    )
    # Account-scoped state: only touch the per-session stores for signed-in
    # users. Anonymous page loads must not allocate a store bucket (login GET would
    # orphan a key before regenerate_session clears the cookie payload).
    authed = current_user().is_authenticated
    starred = watchlist.symbols() if authed else frozenset()
    return {
        "markets": markets,
        "tickers": tickers,
        "sparklines": sparklines,
        "house_token": "$MEOW",
        "meow_balance": balance() if authed else INITIAL_MEOW,
        "watchlist_starred": starred,
        "watchlist_count": len(starred),
        # Topbar notifications bell — the recent feed + the unread count, used to
        # SSR-seed the bell's signal sinks (no empty-then-fill flash). Both are
        # sync, cheap reads; live updates ride the `notifications` SOURCE signal +
        # the derived `notif_badge` / `notif_announce` signals over the single
        # /_chirp/live connection (price-move alerts + fills/deposits), and opening
        # the bell POSTs /notifications/read, which emits so the badge derives to 0.
        "notifications": notifications.recent() if authed else (),
        "notifications_unread": notifications.unread_count() if authed else 0,
        # The Cmd/Ctrl-K command palette directory (every market + the rooms),
        # unfiltered for the resting palette. The /search route re-filters this
        # by query; the layout renders the dialog once as a shell region.
        "palette_groups": palette_results(markets),
        "shell_actions": ShellActions(
            # Primary: the headline call to action. action="deposit" (NOT href)
            # makes shell_actions.html emit data-action="deposit" on the button;
            # the page-content delegator opens #deposit-modal on click. Deposit is
            # a signed-in ACCOUNT action, so it appears only when authenticated —
            # an empty zone for an anonymous visitor (whose topbar shows "Sign in"
            # instead). This is also load-bearing: a visible Deposit for an
            # anonymous user would open the modal whose form POSTs to a
            # @login_required route with hx-swap="none", so the 302 → /login would
            # be silently swallowed. current_user() is LookupError-safe (returns
            # AnonymousUser), so this is safe at startup-check time too.
            primary=ShellActionZone(
                items=(
                    (
                        ShellAction(
                            id="deposit",
                            label="Deposit $MEOW",
                            action="deposit",
                            variant="primary",
                            icon="add",
                        ),
                    )
                    if current_user().is_authenticated
                    else ()
                )
            ),
            # No 'controls' zone: section navigation (Markets, etc.) belongs in
            # the outer icon rail, NOT the topbar. IA doctrine — the topbar is
            # identity + global state + global actions; the outer rail owns
            # top-level destinations. Deposit (primary, a global account action)
            # + About (overflow) are the only topbar actions.
            # Overflow: auto-wrapped into a "More" dropdown by shell_actions.html.
            # The overflow "About" link points home (/). Like the brand/logo it
            # MUST carry the full boosted shell-outlet contract — explicit
            # hx-target/hx-swap + hx-select="#page-content" — or a boosted swap
            # nests the whole shell inside #main (the same "shell duplicates
            # inside itself" bug). chirp-ui's route_link_attrs resolver only emits
            # hx-target + hx-boost (no select); supplying explicit hx attrs here
            # both bypasses that resolver and gives htmx the content selector the
            # rest of the shell uses.
            # NOTE: this overflow "About" link points home (/) and, like the
            # brand/logo, currently renders WITHOUT hx-select="#page-content"
            # (chirp-ui's route_link_attrs resolver emits only hx-target +
            # hx-boost). The brand link works around this by bypassing
            # shell_brand_link; the overflow-dropdown render path ignores
            # ShellAction.attrs, so the same workaround is not available here.
            # Tracked as an upstream chirp-ui finding (route_link_attrs / shell
            # links should carry the content selector the rest of the shell uses).
            overflow=ShellActionZone(
                items=(ShellAction(id="docs", label="About Lucky Cat", href="/", icon="home"),)
            ),
        ),
    }
