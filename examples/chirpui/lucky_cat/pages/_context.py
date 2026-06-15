"""Root context for lucky_cat — markets list, house token, shell actions.

#222: markets now come from the deterministic :class:`SimFeed` behind the
``FeedSource`` seam (``get_feed().markets()``). The sidebar and landing grid
iterate ``markets``; the grid also reads ``tickers`` for live (simulated)
price + 24h change on each card. Snapshot reads are sync and cheap.

#230: the topbar reads like real exchange chrome. The Deposit action is no
longer an inert ``href="#"`` placeholder — it carries ``action="deposit"`` so
``chirpui/shell_actions.html`` renders ``data-action="deposit"`` on the button,
which the page-content delegator wires to the deposit ``<dialog>`` (the kanban
``data-action`` -> ``showModal()`` pattern). The form POSTs to ``/deposit``,
which credits the wallet and OOB-swaps the ``$MEOW`` balance in the topbar. Two
more zones populate the bar: a ``controls`` Markets-home link and an
``overflow`` "More" dropdown.
"""

from dataclasses import dataclass

import notifications
import watchlist
from command_palette import palette_results
from feed import get_feed
from wallet import balance

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


def context() -> dict:
    feed = get_feed()
    markets = feed.markets()
    # Per-symbol ticker snapshot keyed by symbol for the grid cards.
    tickers = {m.symbol: feed.ticker(m.symbol) for m in markets}
    # Per-symbol gradient-area sparkline geometry, computed from the closing price
    # of each warmed candle (oldest→newest). Snapshot reads are sync and cheap; the
    # template renders the precomputed SVG points (lightweight SVG + CSS, no JS).
    sparklines = {
        m.symbol: _sparkline(tuple(c.close for c in feed.candles(m.symbol, limit=32)))
        for m in markets
    }
    # Watchlist — the starred markets behind the rail's first FUNCTIONAL filter
    # lane. `watchlist_starred` is the immutable membership set the market cards /
    # detail header read to render each star's pressed state; `watchlist_count`
    # is the live rail badge figure. Both are sync, cheap reads (one lock); the
    # /watchlist/toggle route mutates the set and re-renders the star + count twins.
    starred = watchlist.symbols()
    return {
        "markets": markets,
        "tickers": tickers,
        "sparklines": sparklines,
        "house_token": "$MEOW",
        "meow_balance": balance(),
        "watchlist_starred": starred,
        "watchlist_count": len(starred),
        # Topbar notifications bell — the recent feed + the unread count, used to
        # SSR-seed the bell's signal sinks (no empty-then-fill flash). Both are
        # sync, cheap reads; live updates ride the `notifications` SOURCE signal +
        # the derived `notif_badge` / `notif_announce` signals over the single
        # /_chirp/live connection (price-move alerts + fills/deposits), and opening
        # the bell POSTs /notifications/read, which emits so the badge derives to 0.
        "notifications": notifications.recent(),
        "notifications_unread": notifications.unread_count(),
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
            overflow=ShellActionZone(
                items=(ShellAction(id="docs", label="About Lucky Cat", href="/", icon="home"),)
            ),
        ),
    }
