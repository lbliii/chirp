"""Lucky Cat — CHIRP wiring layer for the Maneki-neko simulated trading-floor demo.

This file is the framework side of the example: ``App`` setup (``use_chirp_ui``
+ mounted filesystem pages), the secure-by-default middleware stack, live
``signal()`` / ``EventStream`` routes, and the mutation endpoints that pages
call into. Business logic lives in sibling **DOMAIN** modules (``feed``,
``wallet``, ``trade_store``, ``notifications``, …); sections below mark where
each seam starts.

Run from the repo root (never ``app.run()`` in tests — import + ``app.check()``):

    PYTHONPATH=src python examples/chirpui/lucky_cat/app.py
"""

import asyncio
import contextlib
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Avoid sys.modules collision when another example (e.g. kanban_shell's
# ``store`` / forum_shell's ``forum_store``) loaded a same-named module first.
for _name in (
    "feed",
    "store",
    "wallet",
    "account_store",
    "backplane",
    "session_store",
    "shell",
    "navigation",
    "trade_store",
    "notifications",
    "watchlist",
    "users",
):
    _mod = sys.modules.get(_name)
    _file = getattr(_mod, "__file__", None) if _mod is not None else None
    if _file and Path(_file).resolve() != (ROOT_DIR / f"{_name}.py").resolve():
        del sys.modules[_name]

# The ``pages`` package name is shared by every mounted-pages example
# (kanban_shell, forum_shell, …). A sibling example's test can leave a stale
# ``pages``/``pages.*`` in sys.modules (the per-example conftests do not all run
# the shared module purge), so purge any whose file lives outside THIS example
# before the ``from pages._context import hero_chart`` below — otherwise that
# import resolves to a sibling's ``pages._context`` (which has no ``hero_chart``)
# and the whole Lucky Cat suite errors at collection under the shared test run.
for _name in [n for n in list(sys.modules) if n == "pages" or n.startswith("pages.")]:
    _mod = sys.modules.get(_name)
    _file = getattr(_mod, "__file__", None) if _mod is not None else None
    if _file and ROOT_DIR.resolve() not in Path(_file).resolve().parents:
        del sys.modules[_name]

import lobby
import notifications
import session_store
import trade_store
import users
import watchlist
from backplane import bind_emit, get_backplane
from command_palette import palette_results
from feed import DEFAULT_INTERVAL, INTERVALS, get_feed
from navigation import active_route_path, route_state, shell_navigation
from pages._context import hero_chart as build_chart_geometry
from shell import rail_is_collapsed
from wallet import balance as meow_balance
from wallet import deposit as credit_meow

from chirp import (
    OOB,
    App,
    AppConfig,
    EventStream,
    FormAction,
    Fragment,
    Redirect,
    Request,
    ValidationError,
    login_required,
    logout,
    use_chirp_ui,
)
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.middleware.static import StaticFiles

PAGES_DIR = ROOT_DIR / "pages"
STATIC_DIR = ROOT_DIR / "static"

# ---------------------------------------------------------------------------
# CHIRP — app config & ChirpUI shell
#
# from_env() takes NO template_dir/worker_mode, so layer them on with
# dataclasses.replace. worker_mode="async" is required by EventStream routes
# and the live signal bus. A dev fallback secret keeps the example runnable
# without CHIRP_SECRET_KEY; production deploys (env != "development") must set it.
# ---------------------------------------------------------------------------

_base = AppConfig.from_env()
config = replace(
    _base,
    template_dir=PAGES_DIR,
    worker_mode="async",
    # SINGLE worker (not the CPU-count default). This example keeps ALL state in
    # process memory — the wallet, trade store, notifications log, the SimFeed, AND
    # the signal bus (the ReactiveBus behind @app.signal). Multiple OS-process
    # workers would each hold a SEPARATE copy, so state would split across requests
    # (a deposit on one worker invisible to the next) AND the live /_chirp/live SSE
    # connection — pinned to one worker — would stall the page loads that land on a
    # tied-up worker (the "white screen" / freeze). A single-user in-memory demo is
    # inherently single-process. Real multi-worker realtime needs a shared bus
    # inherently single-process today. Scale by implementing SignalBackplane
    # (backplane.py — InProcessBackplane default, RedisBackplane stub) plus an
    # external state store; see DESIGN.md §7 and the signal RFC.
    workers=1,
    # view_transitions="htmx" animates the boosted #main swap on navigation.
    # Keep htmx unset (the chirp-ui shell bundles it) and do NOT add alpine=True
    # (use_chirp_ui owns Alpine — adding it would double-inject).
    view_transitions="htmx",
    secret_key=_base.secret_key or "dev-only-not-for-production",
)

app = App(config=config)

# Signal fan-out seam — routes publish through the backplane instead of calling
# app.emit directly so a Redis adapter can wake every worker's /_chirp/live
# connection when workers>1 (see backplane.RedisBackplane skeleton).
bind_emit(app.emit)


def _signal_audience_key() -> str:
    """The store key for session-scoped signal fan-out (empty for the test default)."""
    key = session_store.session_key()
    return "" if key == session_store.DEFAULT_KEY else key


def emit_signal(name: str, value, *, audience_key: str | None = None) -> None:
    """Push a signal value through the configured backplane (default: in-process)."""
    aud = _signal_audience_key() if audience_key is None else audience_key
    get_backplane().publish(name, value, audience_key=aud)


def fan_out_notifications_live() -> None:
    """Emit each *real* session's bell snapshot over its scoped /_chirp/live topic.

    ``notifications`` is session-scoped, so every emit must target a real session
    key: the framework forbids an empty ``audience_key`` on a session signal (a
    ``ValueError`` that would kill the source pump for the whole connection). The
    DEFAULT_KEY/anonymous bucket has no live audience — anonymous visitors carry
    only global signals and keep their SSR-seeded bell — so ``client_keys()``
    (non-default keys only) skips it instead of coercing it to ``""``.
    """
    for key in session_store.client_keys():
        with session_store.bind(key):
            emit_signal("notifications", notifications.snapshot(), audience_key=key)


use_chirp_ui(app)
app.add_middleware(StaticFiles(directory=STATIC_DIR, prefix="/static"))

# ---------------------------------------------------------------------------
# CHIRP — server-side navigation globals (template context)
#
# Exposed to the layout as template globals. route_state() + shell_navigation()
# recompute the two-tier rail on every (boosted) navigation. Pure-Python, no I/O.
# ---------------------------------------------------------------------------

app.template_global()(route_state)
app.template_global()(shell_navigation)
app.template_global()(active_route_path)
# Server-side rail-collapse preference — read in the layout's head_extra to
# pre-render the collapsed state (no FOUC) and cookie-persisted by
# static/lucky-cat-shell.js.
app.template_global()(rail_is_collapsed)

# ---------------------------------------------------------------------------
# CHIRP — live signals (declare-once / bind-many over /_chirp/live)
# DOMAIN data: feed tickers, wallet balance, notifications log
#
# ONE /_chirp/live connection carries every named topic. A signal is a server
# value fanned out to N bindings: {{ signal('balance') }} in the topbar AND in
# the deposit modal both swap from one `event: balance` — zero hand-maintained
# OOB twins.
#
# - `balance` is PUSH (no source generator): the /deposit and /trade routes call
#   app.emit('balance', new_balance) and every binding updates. The decorated
#   async generator yields nothing — the blessed push-only pattern (the framework
#   pumps it once, it ends immediately, and emit() drives the value thereafter).
# - `ticker` is SOURCE-driven: a rotating market spotlight async generator
#   replaces the deleted /ticker/stream route. Its render emits the SAME
#   ticker_strip_body block the layout paints (one source of truth, no drift).
# - A DERIVED signal recomputes from another signal's value and re-emits to its
#   own bindings in the same emit cascade — the planned `notif_badge` (unread
#   count derived from the notifications list) is the showcase for that fold.
#
# worker_mode="async" (set on the config above) is required: the merge stream is
# an async EventStream and cross-thread emits ride the bus's call_soon_threadsafe.
# ---------------------------------------------------------------------------

# Topbar ticker rotation cadence (seconds). The deterministic sim ticks fast;
# rotating the spotlight on a human-readable window keeps the strip legible
# instead of flashing through every market each tick.
_TICKER_ROTATE_S = 2.5


def _render_ticker_strip(ticker) -> str:
    """Render the cross-page ticker strip body for the `ticker` signal.

    Emits the SAME ticker_strip_body the layout paints (the ticker_signal block
    wraps it with no #lucky-cat-ticker id / hx-swap-oob — the signal_block sink
    owns the wrapper), so the live strip and the initial paint can never drift.
    """
    return app.render(Fragment("_layout.html", "ticker_signal", ticker=ticker))


def _ticker_spotlight():
    """First spotlight ticker for the SSR seed (no empty-then-fill flash)."""
    feed = get_feed()
    markets = feed.markets()
    return feed.ticker(markets[0].symbol) if markets else None


@app.signal("balance", audience="session")
async def balance_signal():  # pragma: no cover - push-only; driven by app.emit
    """PUSH signal for the topbar/modal $MEOW balance. No source — /deposit and
    /trade call app.emit('balance', ...) and every binding swaps in lockstep."""
    if False:
        yield 0


@app.signal("ticker", initial=_ticker_spotlight, render=_render_ticker_strip)
async def ticker_signal():
    """Rotate a live market spotlight through the topbar strip (replaces the old
    /ticker/stream route). One source, one connection, live on every page."""
    feed = get_feed()
    symbols = [m.symbol for m in feed.markets()]
    if not symbols:
        return
    idx = 0
    last_emit = 0.0
    with contextlib.suppress(KeyError):
        async for _tick in feed.subscribe(symbols[0]):
            now = time.monotonic()
            # First tick emits immediately (fills the "Waiting…" hint), then the
            # spotlight advances one market per rotation window.
            if now - last_emit >= _TICKER_ROTATE_S:
                last_emit = now
                symbol = symbols[idx % len(symbols)]
                idx += 1
                yield feed.ticker(symbol)


# ---------------------------------------------------------------------------
# CHIRP — live MARKETS LOBBY board (the compute-once / broadcast-many showcase)
#
# The Markets lobby (/ and /markets) is fully reactive: the stat strip, the movers
# grid (which RE-RANKS live), and the featured spotlight (price + a live redrawing
# sparkline) all update over the SAME single /_chirp/live connection — no second
# sse-connect, no extra page weight.
#
# ONE source signal does the work: `lobby_snapshot` SAMPLES the feed on a human
# cadence (read-only — the `ticker` signal above is the sole engine clock) and emits
# a self-contained lobby.LobbySnapshot. Three @app.derived signals PROJECT that one
# snapshot into the three regions and re-render in lockstep — the genuine derived
# cascade (rank ONCE, fan out to N regions). The snapshot carries per-value
# direction flags so each region flashes only the values that actually moved, and
# the derived stay PURE functions of the snapshot value (no feed/store reads — the
# notif_badge purity contract, applied to the board).
#
# `lobby_snapshot` itself has NO DOM sink (only the three derived do), so its own
# wire event is suppressed (render returns None → the merge stream skips it); it
# exists purely to drive the cascade.
# ---------------------------------------------------------------------------

# Lobby board refresh cadence (seconds). The sim ticks fast; re-ranking + emitting
# on a human-readable window keeps the board legible (and the payload small)
# instead of firehosing a swap every raw tick.
_LOBBY_REFRESH_S = 1.5


def _lobby_snapshot_seed():
    """First lobby snapshot for the SSR/registry seed (no flash, read-only)."""
    return lobby.build_live_snapshot(get_feed(), None)


def _suppress_emit(_value):
    """Render for `lobby_snapshot`: it has no DOM sink, so skip its own wire event
    (the merge stream drops an event whose render returns None). The three derived
    signals still cascade off its cached VALUE."""
    return None


@app.signal("lobby_snapshot", initial=_lobby_snapshot_seed, render=_suppress_emit)
async def lobby_snapshot_signal():
    """SOURCE: sample the feed into a fresh lobby snapshot on a human cadence.

    Read-only sampling — it never advances the engine (the `ticker` signal is the
    clock); each snapshot carries direction flags computed vs the previous one so
    the three derived regions flash only what changed."""
    feed = get_feed()
    symbols = [m.symbol for m in feed.markets()]
    if not symbols:
        return
    prev = None
    while True:
        await asyncio.sleep(_LOBBY_REFRESH_S)
        snap = lobby.build_live_snapshot(feed, prev)
        prev = snap
        yield snap


def _render_lobby_stats(value) -> str:
    """Render the stat strip body for the derived `market_stats` signal."""
    stats, dirs = value
    return app.render(Fragment("markets/page.html", "stat_strip_signal", stats=stats, dirs=dirs))


def _render_lobby_movers(value) -> str:
    """Render the movers grid body for the derived `movers` signal."""
    movers, dirs = value
    return app.render(Fragment("markets/page.html", "movers_signal", movers=movers, dirs=dirs))


def _render_lobby_featured(value) -> str:
    """Render the featured spotlight body for the derived `featured` signal."""
    market, ticker, spark, direction = value
    return app.render(
        Fragment(
            "markets/page.html",
            "featured_signal",
            market=market,
            t=ticker,
            spark=spark,
            dir=direction,
        )
    )


@app.derived("market_stats", on=("lobby_snapshot",), render=_render_lobby_stats)
def lobby_stats_derived(snap):
    """PURE projection: the stat strip data + its flash directions."""
    return (snap.stats, snap.stat_dirs)


@app.derived("movers", on=("lobby_snapshot",), render=_render_lobby_movers)
def lobby_movers_derived(snap):
    """PURE projection: the ranked movers segments + per-row flash directions."""
    return (snap.movers, snap.mover_dirs)


@app.derived("featured", on=("lobby_snapshot",), render=_render_lobby_featured)
def lobby_featured_derived(snap):
    """PURE projection: the featured spotlight market / ticker / sparkline + flash."""
    return (snap.featured_market, snap.featured_ticker, snap.featured_spark, snap.featured_dir)


# ---------------------------------------------------------------------------
# Notifications — the topbar bell, folded onto the ONE /_chirp/live connection.
#
# This is the headline N→1 fold: the old shell opened a SECOND persistent SSE
# scope (/notifications/stream) on every page. That stream is now the
# `notifications` SIGNAL — a SOURCE-driven async generator carrying the SAME
# drain + price-move-alert loop — so the app holds exactly ONE sse-connect.
#
# - `notifications` is SOURCE-driven: its generator runs the price-alert
#   hysteresis + cooldown walk and, whenever the log changes, yields a fresh
#   notifications.snapshot() — a NotifFeed carrying BOTH the recent rows AND the
#   watermark-aware unread count, captured atomically (coalescing-latest). Its
#   render emits the notification_list_body block the bell already paints from
#   feed.notes, so the live list and the initial paint share one body and can
#   never drift.
# - `notif_badge` is DERIVED from `notifications`: a COUNT read PURELY from the
#   emitted value (feed.unread) — the genuine `@app.derived` showcase. It
#   recomputes + re-emits in the same cascade whenever `notifications` changes.
#   It must NOT re-read the store: a derived is a pure function of its INPUT
#   SIGNAL VALUES (deterministic across workers, race-free across threads) — the
#   snapshot already bundled the count with the rows it ships.
# - `notif_announce` is DERIVED too (also feed.unread): its render emits the
#   visually-hidden spoken-count body so a11y keeps working.
#
# CRITICAL: the bell's sinks are EXISTING elements (the <ul id="notif-list">,
# the <span id="notif-badge">, the <span id="notif-announce">), so the layout
# binds them with a MANUAL `sse-swap="..."` attribute on each element (NOT the
# signal_block() helper, which would inject its own <div> wrapper around/inside
# the <ul> — invalid + wrong). The signal dead-binding contract scans those
# literal sse-swap attrs under the signal connect, so they ARE validated.
# ---------------------------------------------------------------------------

# Price-move alert threshold: raise a "price" notification when a market's 24h
# change crosses another whole step (in either direction) from the last value
# the signal source alerted on. A whole-step gap keeps the bell from flooding on
# the per-tick walk while still surfacing meaningful moves.
_PRICE_ALERT_STEP_PCT = 2.5
# Per-symbol cooldown (seconds). The deterministic sim ticks fast and its 24h pct
# oscillates with amplitude > the step, so hysteresis alone still ping-pong-fires;
# a cooldown caps each market to one alert per window so the bell can't firehose.
_PRICE_ALERT_COOLDOWN_S = 20.0


def _render_notification_list(feed) -> str:
    """Render the bell dropdown list body for the `notifications` signal.

    The signal VALUE is a :class:`notifications.NotifFeed` carrying both the rows
    and the unread count (the pure-derived contract); this render uses only
    ``feed.notes``. Emits the SAME notification_list_body the layout paints into
    the <ul id="notif-list"> on the initial render (one source of truth, no
    drift), via the notification_list_signal {% fragment %} wrapper (render_fragment
    addresses blocks/fragments, not {% def %} macros). The manual
    sse-swap="notifications" on that <ul> innerHTML-swaps this on every
    `event: notifications` over /_chirp/live.
    """
    return app.render(Fragment("_layout.html", "notification_list_signal", notes=feed.notes))


def _render_notif_badge(unread: int) -> str:
    """Render the unread-count pill body for the `notif_badge` derived signal."""
    return app.render(Fragment("_layout.html", "notif_badge_signal", unread=unread))


def _render_notif_announce(unread: int) -> str:
    """Render the visually-hidden spoken-count body for `notif_announce`."""
    return app.render(Fragment("_layout.html", "notif_announce_signal", unread=unread))


@app.signal(
    "notifications",
    audience="session",
    render=_render_notification_list,
)
async def notifications_signal():
    """Live notifications SOURCE — drain the log + raise price-move alerts.

    One async loop, pumped by the merge stream so it runs on every page (the
    fold of the old /notifications/stream route onto /_chirp/live). Per
    simulated tick it scans every market's 24h change and, when one crosses
    another whole step from the last alerted level (hysteresis) AND its
    per-symbol cooldown has elapsed, appends a "price" notification via
    ``notifications.add_broadcast`` — so price alerts flow through the SAME log as fills
    and deposits (one source of truth, one badge count). Whenever the log
    changes it calls :func:`fan_out_notifications_live` (scoped per session).

    Push-only on the wire: the ``yield`` below exists only so this function is
    an async *generator* (the pump keeps it alive on a background task); live
    updates fan out imperatively via ``emit_signal``, not by yielding snapshots.
    """
    if False:  # pragma: no cover - type marker for the signal pump
        yield notifications.snapshot()
    feed = get_feed()
    symbols = [m.symbol for m in feed.markets()]
    if not symbols:
        return
    # Track the head id so we only re-emit when the log actually grows (fills /
    # deposits push via emit_signal; price alerts below push via add_broadcast).
    last_id = session_store.max_notification_head_id()
    # Per-symbol last-ALERTED 24h pct. Alert only when a market moves a full step
    # FROM that level (hysteresis) — a pct jittering across a fixed bucket
    # boundary must NOT re-fire every tick. Seeded from the current pct so a
    # fresh connection doesn't burst on connect.
    alerted: dict[str, float] = {sym: feed.ticker(sym).change_pct_24h for sym in symbols}
    last_alert_t: dict[str, float] = {}
    with contextlib.suppress(KeyError):
        async for _tick in feed.subscribe(symbols[0]):
            now = time.monotonic()
            # A genuine move (>= one step from the last alerted level) AND a
            # per-symbol cooldown, so a fast volatile sim can't firehose the bell.
            for symbol in symbols:
                snap = feed.ticker(symbol)
                pct = snap.change_pct_24h
                if (
                    abs(pct - alerted[symbol]) >= _PRICE_ALERT_STEP_PCT
                    and now - last_alert_t.get(symbol, 0.0) >= _PRICE_ALERT_COOLDOWN_S
                ):
                    # Headline follows the universal ticker convention: the arrow
                    # tracks the SIGN of the 24h pct shown beside it, so
                    # "PAW-MEOW ▲ +22.36%" never reads as a contradiction. The
                    # move-from-baseline (the `if` above) is the FIRING rule, not
                    # the glyph — a coin can tick down yet still be green.
                    notifications.add_broadcast(
                        "price",
                        f"{symbol} {'▲' if pct >= 0 else '▼'} {pct:+.2f}%",
                        f"Now {snap.price} MEOW.",
                    )
                    alerted[symbol] = pct
                    last_alert_t[symbol] = now
            # Emit a fresh snapshot per session whenever ANY bucket's log grew.
            head = session_store.max_notification_head_id()
            if head != last_id:
                last_id = head
                fan_out_notifications_live()


@app.derived("notif_badge", on=("notifications",), render=_render_notif_badge)
def notif_badge(feed) -> int:
    """Unread badge — a COUNT derived PURELY from the `notifications` VALUE.

    The genuine `@app.derived` showcase: it recomputes whenever `notifications`
    changes and re-emits to every `sse-swap="notif_badge"` binding in the same
    cascade. The pure-derived contract — it reads ONLY ``feed.unread`` from the
    emitted :class:`notifications.NotifFeed`, never ``notifications.unread_count()``
    (a process-local store read is non-deterministic across workers AND can race
    the watermark on a different thread). The snapshot already captured the count
    atomically with the rows, so the badge can never disagree with the list."""
    return feed.unread


@app.derived("notif_announce", on=("notifications",), render=_render_notif_announce)
def notif_announce(feed) -> int:
    """Spoken unread count — derived PURELY from the `notifications` VALUE.

    Drives the visually-hidden #notif-announce live region so the count change is
    announced exactly once, keeping a11y working over the signal connection. Like
    `notif_badge` it reads ONLY ``feed.unread`` (the pure-derived contract — no
    store read)."""
    return feed.unread


# ---------------------------------------------------------------------------
# CHIRP — secure-by-default middleware stack (Session -> Auth -> CSRF -> SecurityHeaders)
#
# Auth slots in between Session and CSRF (the order chirp's auth subsystem
# prescribes, and the order the csrf_session contract requires: Session before
# CSRF — adjacency is not required, so Auth in the middle is fine). Lucky Cat is
# public-browse / gated-trading: AuthMiddleware authenticates every request
# (anonymous when there is no session), and the gated routes/pages enforce
# @login_required. secure cookies use the "auto" default: Secure in
# production/staging (resolved from AppConfig.env, wired via from_env above),
# off in local dev so plain http works.
# ---------------------------------------------------------------------------


async def load_user(user_id: str) -> users.User | None:
    """AuthConfig.load_user — resolve the session's user id back to a User.

    Called by AuthMiddleware on every request that carries a session. The demo
    has a single shared in-memory account (see users.py / DESIGN.md §7), so this
    is a cheap dict read behind the store lock.
    """
    return users.get(user_id)


class _EnsureStoreKeyMiddleware:
    """Assign a per-browser ``__store_key`` on every session for isolated demo state."""

    async def __call__(self, request, next):
        session_store.ensure_store_key()
        return await next(request)


class _SessionSignalsMiddleware:
    """Seed session-scoped signal SSR + bind the SSE audience for this visitor."""

    async def __call__(self, request, next):
        from chirp.realtime.signal_globals import reset_signal_audience, set_signal_audience

        session_store.ensure_store_key()
        key = session_store.session_key()
        aud = _signal_audience_key()
        token = set_signal_audience(aud)
        registry = app._mutable_state.signal_registry
        try:
            from chirp.middleware.auth import current_user

            if registry is not None and aud and current_user().is_authenticated:
                with session_store.bind(key):
                    registry.seed("balance", meow_balance(), audience_key=aud)
                    registry.seed("notifications", notifications.snapshot(), audience_key=aud)
            elif not current_user().is_authenticated:
                # Anonymous pages carry only global signals (ticker, lobby) — no
                # per-visitor audience on the SSE connection.
                reset_signal_audience(token)
                token = set_signal_audience("")
            return await next(request)
        finally:
            reset_signal_audience(token)


# Starlette/chirp wrap order: last-added middleware is innermost and runs closest
# to the app on the way IN — so Session must be registered before EnsureStoreKey
# and SessionSignals (both need get_session() / __store_key on the request).
app.add_middleware(
    SessionMiddleware(
        SessionConfig(
            secret_key=config.secret_key,
            cookie_name="chirp_session_lucky_cat",
            # secure defaults to "auto" — Secure in production/staging via
            # AppConfig.env, off in local dev.
            httponly=True,
            samesite="lax",
        )
    )
)
app.add_middleware(_EnsureStoreKeyMiddleware())
# Auth before SessionSignals so seeding can gate on current_user().is_authenticated
# (anonymous /login must not allocate a store bucket via balance/notifications seed).
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user, login_url="/login")))
app.add_middleware(_SessionSignalsMiddleware())
app.add_middleware(CSRFMiddleware(CSRFConfig()))
# SecurityHeaders for the clickjacking / MIME-sniff / referrer headers only —
# content_security_policy=None so it does NOT emit a CSP header. use_chirp_ui
# (called above) flipped csp_nonce_enabled, so the compiler wires
# CSPNonceMiddleware as the single CSP authority: a per-request nonce script-src
# plus 'unsafe-eval' and style-src 'unsafe-inline' that chirp-ui's Alpine shell
# requires. No hand-written CSP — the chirpui_csp contract check would WARN/ERROR
# if a future edit re-broke it.
app.add_middleware(SecurityHeadersMiddleware(SecurityHeadersConfig(content_security_policy=None)))

# ---------------------------------------------------------------------------
# DOMAIN — mutation & fragment routes (registered BEFORE mount_pages)
# ---------------------------------------------------------------------------


@app.route("/health")
def health():
    """Unauthenticated Railway healthcheck."""
    return ("ok", 200)


@app.route("/logout", methods=["POST"], name="logout")
def do_logout():
    """Sign out — regenerate the session and full-page redirect home.

    The user-menu Sign-out form (in _layout.html) posts here. ``logout()``
    regenerates the session (discarding the user id + all session data) and sets
    the request user back to anonymous. Like the login success path, this returns
    a ``FormAction`` (no fragments) → HX-Redirect with no Location for htmx (a
    FULL ``window.location`` page load) so the persistent topbar repaints to the
    logged-out chrome (user menu → "Sign in", account chrome disappears), and a
    303 for a plain POST. (A 303 + Location alone is auto-followed by htmx's XHR
    before it acts on HX-Redirect, leaving the URL stuck.) CSRF is enforced by
    the shared secure stack.
    """
    logout()
    return FormAction("/")


_PALETTE_TEMPLATE = "_components/command_palette.html"


@app.route("/search", referenced=True)
def search(request: Request):
    """Filter the command-palette directory by ``q`` and re-render the results.

    The Cmd/Ctrl-K palette's search input ``hx-get``s here on every keystroke
    (debounced) and swaps the response into ``#command-palette-results``. The
    response is the ``palette_results_body`` block — the SAME block the layout
    renders for the resting palette — so the markup can never drift. ``q`` is
    matched case-insensitively against each market's symbol + display name and
    each room's key + label; an empty query returns the full directory.

    A GET-only, read-only route (no CSRF needed). ``referenced=True`` marks it as
    fetched-via-htmx-only (never an ``<a href>``), so ``app.check()``'s
    orphan-route rule stays quiet and the ``test_links`` crawl never visits it.
    """
    query = (request.query.get("q") or "").strip()
    groups = palette_results(get_feed().markets(), query)
    return Fragment(
        _PALETTE_TEMPLATE,
        "palette_results_body",
        groups=groups,
        query=query,
    )


@app.route("/deposit", methods=["POST"], name="deposit")
@login_required
async def deposit(request: Request):
    """Credit the house token and emit the balance signal.

    The first mutating route in the example — which is why the secure-by-default
    stack (Session -> CSRF -> SecurityHeaders) was pre-wired. The deposit modal's
    form posts here with ``hx-swap="none"``; CSRF is enforced by ``CSRFMiddleware``
    (the form carries ``csrf_field()`` and the shell layout sets ``X-CSRF-Token``
    on ``htmx:configRequest``).

    The balance is now a live ``signal``: ``app.emit('balance', new_balance)`` fans
    one ``event: balance`` out to EVERY ``{{ signal('balance') }}`` binding (the
    topbar token AND the deposit modal line) over the single ``/_chirp/live``
    connection — and any derived signal recomputes and re-emits in the same
    cascade. No hand-maintained OOB twin: declare once, bind many.

    A malformed/missing amount is clamped to a no-op credit in ``wallet.deposit``,
    so the balance never goes backwards on bad input. The HTTP response itself is
    an empty 204 (the form posts with ``hx-swap="none"``); the visible update flows
    over the live signal connection, not this response body.
    """
    form = await request.form()
    raw = form.get("amount", "")
    try:
        amount = int(raw)
    except ValueError, TypeError:
        amount = 0
    new_balance = credit_meow(amount)
    # Fan the new balance out to every binding (topbar + modal) over /_chirp/live.
    # Any derived signal recomputes in the same emit cascade, so its bindings stay
    # in sync too — one producer, many homes.
    emit_signal("balance", new_balance)
    # Log a deposit notification only for a real credit (a clamped bad amount is a
    # no-op, so it never reaches the bell — mirroring wallet.deposit's ledger).
    credit = max(0, amount)
    if credit > 0:
        notifications.add(
            "deposit",
            f"Deposited {credit} $MEOW",
            f"Balance now {new_balance} $MEOW.",
        )
        # Emit the `notifications` signal (a fresh snapshot — rows + unread count,
        # atomic) so the bell reacts IMMEDIATELY (the dropdown list re-renders + the
        # derived badge/announce recompute PURELY from feed.unread in the same
        # cascade) — not only on the next feed tick. One log, fanned out.
        emit_signal("notifications", notifications.snapshot())
    # hx-swap="none" ignores the body; the live signal carries the visible update.
    return ("", 204)


# ---------------------------------------------------------------------------
# Watchlist — a thread-safe starred-markets set behind the rail's Favorites
# destination (the /markets/favorites page renders the starred-only grid). The
# per-card / detail-header star <button> POSTs here; the route flips the star and
# returns TWO OOB twins: the star control itself (so aria-pressed + the ★/☆ glyph
# flip in place) and the rail count badge (so the Favorites tally stays honest on
# every page). The one mutating watchlist route, covered by the secure-by-default
# stack (CSRF enforced). The POST route keeps its /watchlist/toggle name (it is a
# referenced mutation, never an <a href>), even though the VIEW moved to
# /markets/favorites.
# ---------------------------------------------------------------------------


@app.route("/watchlist", name="watchlist.moved")
def watchlist_moved():
    """Permanent redirect for the moved Favorites page.

    The starred-markets VIEW moved from ``/watchlist`` to ``/markets/favorites``
    (one of the four fixed Markets destinations). A 308 (Permanent Redirect)
    keeps stale bookmarks / external links alive and tells crawlers the resource
    moved for good — without it ``/watchlist`` would 404. 308 (not 301/302)
    preserves the method, so a same-URL ``HEAD``/GET resolves cleanly. The
    mutating ``/watchlist/toggle`` POST keeps its name (it is a referenced
    htmx mutation, never an ``<a href>``), so only the GET page redirects.
    """
    return Redirect("/markets/favorites", status=308)


@app.route("/watchlist/toggle", methods=["POST"], name="watchlist.toggle")
@login_required
async def watchlist_toggle(request: Request):
    """Flip a market's starred state and OOB-swap the star + rail count twins.

    The star <button> on each market card / detail header hx-posts here with the
    market ``symbol`` in the form body. Because the control lives inside the
    boosted app-shell (``hx-target=#main`` / ``hx-select=#page-content`` inherited
    from ancestors), the button OVERRIDES those with ``hx-swap="none"`` +
    ``hx-select`` of its OWN star fragment id — so htmx applies only the two OOB
    swaps and never churns ``#main`` (override inherited ``hx-target`` with
    ``hx-select`` on the trigger — ``hx-disinherit`` only affects descendants).

    The response bakes both OOB targets itself: the
    ``#watchlist-star-{symbol}`` star control (innerHTML re-render of the toggling
    button's body, with the new ``aria-pressed`` / ★/☆) and the
    ``#watchlist-count`` rail badge (innerHTML). Unknown symbols are a no-op flip
    (the set never gains a non-market), so a tampered body can't pollute the lane.

    Free-threading safety: ``watchlist.toggle`` flips the set under one lock, so
    two concurrent toggles of the same symbol can never leave the count drifting
    from the rendered stars.
    """
    feed = get_feed()
    form = await request.form()
    symbol = (form.get("symbol") or "").strip()
    known = (
        feed.has_symbol(symbol)
        if hasattr(feed, "has_symbol")
        else any(m.symbol == symbol for m in feed.markets())
    )
    # Unknown/blank symbol → a no-op flip (re-render the current state so the swap
    # is still well-formed: never a 500, never a polluted set). A known symbol
    # flips atomically and returns the NEW starred state.
    starred = watchlist.contains(symbol) if not symbol or not known else watchlist.toggle(symbol)
    # Two OOB targets in one response: the star control
    # itself (primary — emitted verbatim, its baked #watchlist-star-{symbol} id +
    # hx-swap-oob lets htmx swap it in place) and the rail count badge sibling
    # (#watchlist-count, registered wrap=False so its baked wrapper is emitted
    # verbatim too). The toggling <button> posts with hx-swap="none" + an
    # hx-select of its own star fragment, so #main never churns.
    fragments: list[Fragment] = [
        Fragment(
            "_components/market.html",
            "watchlist_star_swap",
            symbol=symbol,
            starred=starred,
        ),
        Fragment(
            "_layout.html",
            "watchlist_count_swap",
            target="watchlist-count",
            watchlist_count=watchlist.count(),
        ),
    ]
    # Unstar-on-Favorites polish: when the toggle originated ON /markets/favorites
    # AND the result is unstarred, append a THIRD OOB twin that removes the card
    # cell live (hx-swap-oob="delete" on #luckycat-card-{symbol}), so the
    # starred-only grid stays a one-glance view of exactly the stars (no stale ☆
    # card lingering until reload). htmx sends the originating URL in
    # HX-Current-URL; we read its path only (queryless) so a fragment/query can't
    # fool it. On the landing / detail pages the toggle is left reversible in place
    # — only /markets/favorites prunes. The #luckycat-card-{symbol} id only exists
    # on grid pages, so the delete is a harmless no-op elsewhere (the cancel-route
    # orders_table_oob precedent).
    if symbol and known and not starred:
        current_url = request.headers.get("HX-Current-URL", "")
        if active_route_path(current_url) == "/markets/favorites":
            fragments.append(
                Fragment(
                    "_components/market.html",
                    "watchlist_card_remove",
                    symbol=symbol,
                )
            )
    return OOB(*fragments)


# ---------------------------------------------------------------------------
# Notifications bell — the mutating route. /trade/order + /deposit append
# fill/deposit entries (and emit the `notifications` signal); the live drain +
# price-move-alert walk is now the `notifications` SIGNAL declared above (one
# fewer persistent connection). Opening the bell POSTs /notifications/read
# (open-marks-read) and emits the signal so the derived badge/announce clear —
# the one mutating notifications route, covered by the secure-by-default stack.
# ---------------------------------------------------------------------------


@app.route("/notifications/read", methods=["POST"], name="notifications.read")
@login_required
def notifications_read():
    """Mark every notification read and clear the badge over the signal connection.

    Opening the bell hx-posts here (open-marks-read). It marks the log read, then
    EMITS the `notifications` signal so the derived `notif_badge` + `notif_announce`
    recompute to 0 and every binding clears over the single /_chirp/live
    connection — no hand-maintained OOB badge twin. The HTTP response is an empty
    204 (the trigger posts with hx-swap="none"); the visible clear flows over the
    live signal connection, not this response body. CSRF is enforced by
    CSRFMiddleware (the shell sets X-CSRF-Token on htmx requests).
    """
    notifications.mark_all_read()
    # Re-emit a fresh snapshot (same rows, unread now 0 after the watermark
    # advance) so the derived badge + announce recompute PURELY from feed.unread
    # to 0 and fan out to every binding over /_chirp/live.
    emit_signal("notifications", notifications.snapshot())
    return ("", 204)


# ---------------------------------------------------------------------------
# DOMAIN — trade flow (place + cancel orders against SimFeed + house wallet)
# CHIRP return types: FormAction + ValidationError + multi-target OOB
# ---------------------------------------------------------------------------

_TRADE_TEMPLATE = "trade/page.html"
_TOAST_TEMPLATE = "_components/toast_oob.html"


def _toast(message: str, variant: str = "success") -> Fragment:
    """Toast OOB fragment (chirp-ui macro bakes hx-swap-oob beforeend:#chirpui-toasts)."""
    return Fragment(_TOAST_TEMPLATE, "toast", message=message, variant=variant)


def _fill_fragments() -> tuple[Fragment, ...]:
    """The shared OOB set for a fill: positions table + open-order count.

    The toast and the (reset) form are appended by the caller so the htmx and
    plain-POST paths share the data-bearing fragments. The topbar $MEOW balance is
    NO LONGER an OOB twin here — it is a live ``signal``: the caller emits the new
    balance (``app.emit('balance', ...)``) and every binding (topbar + modal)
    swaps from the shared /_chirp/live connection, with any derived signal
    recomputing in the same cascade.
    """
    return (
        Fragment(_TRADE_TEMPLATE, "positions_oob", positions=trade_store.positions()),
        Fragment(
            _TRADE_TEMPLATE,
            "open_order_count_oob",
            open_order_count=trade_store.open_order_count(),
        ),
    )


@app.route("/trade/order", methods=["POST"], name="trade.order")
@login_required
async def place_order(request: Request):
    """Place an order. Invalid -> 422 + re-rendered form; filled -> one OOB swap.

    Validation (insufficient balance / below min size / bad limit price) returns
    ``ValidationError("trade/page.html", "order_form", ...)`` -> 422 with field
    errors and the submitted values preserved (no full-page nav). A clean order
    fills via ``trade_store`` and returns a ``FormAction``: htmx gets the OOB
    fragments (positions row + topbar $MEOW balance + open-order count + toast,
    with the form reset as the primary swap), a plain POST gets a 303 redirect
    back to ``/trade``. CSRF is enforced by ``CSRFMiddleware`` (the form carries
    ``csrf_field()`` and the shell sets ``X-CSRF-Token`` on htmx requests).

    Free-threading safety (this example's whole point): the fill goes through
    ``trade_store.try_place_order``, which re-checks the balance and debits the
    wallet inside a single lock. So two concurrent buys racing the same balance
    can never both win — the loser gets a clean 422, never an unhandled
    ``ValueError`` 500. The pre-fill ``validate_order`` still produces the rich
    field errors (min size / bad limit / unknown symbol); the atomic re-check is
    the last word on whether the buy actually clears.
    """
    feed = get_feed()
    markets = feed.markets()
    form = await request.form()
    symbol = (form.get("symbol") or "").strip()
    side = (form.get("side") or "buy").strip()
    kind = (form.get("kind") or "market").strip()
    size_raw = (form.get("size") or "").strip()
    limit_raw = (form.get("limit_price") or "").strip()
    values = {
        "symbol": symbol,
        "side": side,
        "kind": kind,
        "size": size_raw,
        "limit_price": limit_raw,
    }

    errors, parsed = trade_store.validate_order(symbol, side, kind, size_raw, limit_raw)
    if errors:
        return ValidationError(
            _TRADE_TEMPLATE,
            "order_form",
            errors=errors,
            form=values,
            markets=markets,
        )

    # Limit orders REST (book an open order) rather than fill: the M2 sim has no
    # matching engine, so a limit order joins the open-orders book and bumps the
    # live #open-order-count badge. (A market order fills immediately below.)
    if kind == "limit":
        resting = trade_store.open_limit_order(symbol, side, parsed["size"], parsed["limit_price"])
        return FormAction(
            "/trade",
            # Reset the form, then OOB-swap the open-order count + a toast.
            Fragment(_TRADE_TEMPLATE, "order_form", markets=markets, form={}, errors=None),
            Fragment(
                _TRADE_TEMPLATE,
                "open_order_count_oob",
                open_order_count=trade_store.open_order_count(),
            ),
            _toast(
                f"Resting {resting.side} {resting.size:g} {resting.symbol} "
                f"@ {resting.limit_price:g}.",
                variant="info",
            ),
            trigger="orderResting",
        )

    order, fill_errors = trade_store.try_place_order(
        symbol,
        side,
        kind,
        parsed["size"],
        parsed["limit_price"],
        fill_price=parsed["fill_price"],
    )
    if order is None:
        # The atomic balance re-check rejected the fill — e.g. a concurrent buy
        # spent the balance between validate_order and the debit. Surface it as
        # the same 422 field error, never a 500.
        return ValidationError(
            _TRADE_TEMPLATE,
            "order_form",
            errors=fill_errors,
            form=values,
            markets=markets,
        )

    # Log a fill notification so the topbar bell mirrors the toast, then EMIT the
    # `notifications` signal so the bell reacts immediately (the dropdown list
    # re-renders + the derived badge/announce recompute in the same cascade) and
    # fans out to every open tab over the single /_chirp/live connection.
    notifications.add(
        "fill",
        f"Filled {order.side} {order.size:g} {order.symbol}",
        f"@ {order.size * parsed['fill_price']:g} $MEOW.",
    )
    emit_signal("notifications", notifications.snapshot())
    # A fill debits the wallet — fan the new balance out to every signal binding
    # (topbar + modal); any derived signal recomputes in the same cascade.
    emit_signal("balance", meow_balance())
    return FormAction(
        "/trade",
        # Primary swap: reset the form (no errors, empty values).
        Fragment(_TRADE_TEMPLATE, "order_form", markets=markets, form={}, errors=None),
        *_fill_fragments(),
        _toast(f"Filled {order.side} {order.size:g} {order.symbol}.", variant="success"),
        trigger="orderFilled",
    )


_ORDERS_TEMPLATE = "portfolio/orders/page.html"


@app.route("/trade/order/{order_id}/cancel", methods=["POST"], name="trade.cancel")
@login_required
def cancel_order(order_id: int):
    """Cancel a resting order and OOB-swap the open-order count + a toast.

    The per-row Cancel form deletes its own ``<tr>`` (a local ``hx-swap="delete"``
    that overrides the inherited boosted-shell outlet attrs), so the count badge
    OOB swap alone keeps both /trade and /portfolio/orders honest. But cancelling
    the LAST resting order would leave the orders page showing a bare table
    (thead with no rows) until reload — the row deleted itself, yet the
    empty-state never appeared. So when the book hits zero we ALSO OOB-swap the
    ``#open-orders-table`` container to the empty-state. That fragment bakes its
    own ``#open-orders-table`` id (fail-loud against a real target): the id only
    exists on /portfolio/orders, so the swap is a harmless no-op on /trade (whose
    cancel control is the same form). Cancelling a non-last order leaves the
    container untouched (the row-delete handles it) — no wasteful full-table swap.
    """
    cancelled = trade_store.cancel_order(order_id)
    message = "Order cancelled." if cancelled is not None else "Order not found."
    variant = "info" if cancelled is not None else "warning"
    fragments: list[Fragment] = [
        Fragment(
            _TRADE_TEMPLATE,
            "open_order_count_oob",
            open_order_count=trade_store.open_order_count(),
        ),
    ]
    if trade_store.open_order_count() == 0:
        # Book emptied — repaint the orders-page container as the empty-state so
        # it never shows a bare thead until reload. Harmless on /trade (no such id).
        fragments.append(Fragment(_ORDERS_TEMPLATE, "orders_table_oob", orders=()))
    return FormAction(
        "/trade",
        *fragments,
        _toast(message, variant=variant),
        trigger="orderCancelled",
    )


@app.route("/trade/convert", methods=["POST"], name="trade.convert")
@login_required
async def convert_order(request: Request):
    """Convert $MEOW into a market (a market buy) from Trade → Convert.

    Self-contained so a validation failure re-renders the CONVERT form, not the
    spot order_form: an htmx submit swaps #convert-form in place (422); a plain
    (no-JS) POST redirects back to the shell-bearing convert page rather than
    replacing the document with a bare fragment. A clean fill redirects to /trade.
    """
    feed = get_feed()
    markets = feed.markets()
    form = await request.form()
    symbol = (form.get("symbol") or "").strip()
    size_raw = (form.get("size") or "").strip()
    values = {"symbol": symbol, "size": size_raw}

    errors, parsed = trade_store.validate_order(symbol, "buy", "market", size_raw, "")
    if not errors:
        order, fill_errors = trade_store.try_place_order(
            symbol,
            "buy",
            "market",
            parsed["size"],
            parsed["limit_price"],
            fill_price=parsed["fill_price"],
        )
        if order is None:
            errors = fill_errors

    if errors:
        if request.headers.get("HX-Request") == "true":
            return Fragment(
                "trade/convert/page.html",
                "convert_form",
                errors=errors,
                form=values,
                markets=markets,
            )
        # Plain POST: redirect back to the shell-bearing convert page (never a
        # bare, shell-less 422 fragment that would replace the whole document).
        return FormAction("/trade/convert")

    # The convert debited $MEOW into a position — fan the new balance out to every
    # signal binding (and recompute any derived signal) over /_chirp/live.
    emit_signal("balance", meow_balance())
    return FormAction(
        "/trade",
        # Primary swap: reset the convert form in place (hx-select="#convert-form"
        # on the form picks this out of the response). Then an OOB toast — the
        # balance flows over the live signal connection, not an OOB twin.
        Fragment("trade/convert/page.html", "convert_form", markets=markets, errors=None, form={}),
        _toast(f"Converted {parsed['size']:g} $MEOW into {symbol}.", variant="success"),
        trigger="orderFilled",
    )


# ---------------------------------------------------------------------------
# DOMAIN + CHIRP — free-threading proof panel (live ticks/sec via EventStream)
#
# Streams a ticks/sec figure into the portfolio dashboard's #ft-panel. SimFeed
# fans every tick across its worker pool; this route reads the observability-only
# tick counter and OOB-swaps a derived rate.
# ---------------------------------------------------------------------------

_PORTFOLIO_TEMPLATE = "portfolio/page.html"


@app.route("/ft/stream", referenced=True)
def ft_stream():
    """Live free-threading proof: OOB-swap the ticks/sec figure each window.

    Subscribes to the feed (which advances every symbol per tick across the
    worker pool, bumping the thread-safe counter) and yields one ``ft_panel_oob``
    fragment per tick, computing ticks/sec from the counter delta over the
    wall-clock window. ``referenced=True`` marks it as sse-connect-only so the
    orphan-route check stays quiet; the fragment bakes ``#ft-panel`` +
    ``hx-swap-oob`` itself (the ticker/balance SSE-twin idiom).

    The counter feeds only this display — never the price engine — so it cannot
    perturb the deterministic tick sequence. The figure honestly reads parallel
    throughput: high on a ``python3.14t`` (GIL-disabled) build, GIL-bound here.
    """
    import time

    feed = get_feed()
    symbols = [m.symbol for m in feed.markets()]
    gil_enabled = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
    workers = getattr(feed, "worker_count", 0)
    markets = getattr(feed, "market_count", len(symbols))

    async def generate():
        if not symbols:
            return
        last_count = feed.tick_count() if hasattr(feed, "tick_count") else 0
        last_ts = time.monotonic()
        with contextlib.suppress(KeyError):
            async for _tick in feed.subscribe(symbols[0]):
                now = feed.tick_count() if hasattr(feed, "tick_count") else last_count
                wall = time.monotonic()
                elapsed = wall - last_ts
                rate = round((now - last_count) / elapsed, 1) if elapsed > 0 else 0.0
                last_count, last_ts = now, wall
                yield Fragment(
                    _PORTFOLIO_TEMPLATE,
                    "ft_panel_oob",
                    ft_gil_enabled=gil_enabled,
                    ft_workers=workers,
                    ft_markets=markets,
                    ft_ticks_per_sec=rate,
                )

    return EventStream(generate())


# The cross-page topbar ticker strip moved to the `ticker` SIGNAL (declared near
# the top of this module): one rotating-spotlight source over the single
# /_chirp/live connection, replacing the deleted /ticker/stream sse_scope.

# Detail-page template that owns the live blocks. Dynamic-route templates keep
# the literal {symbol} segment as their mounted key.
_DETAIL_TEMPLATE = "markets/{symbol}/page.html"


@app.route("/markets/{symbol}/chart", referenced=True)
def market_chart(symbol: str, request: Request):
    """Hero area chart fragment for one market + timeframe (the toggle target).

    The segmented timeframe toggle in the market hero ``hx-get``s this route per
    timeframe and swaps the ``#market-chart`` region in place. Because the toggle
    lives inside the boosted shell (``#main`` / ``hx-select=#page-content``
    inherited from ancestors), each button OVERRIDES those with
    ``hx-target="#market-chart"`` + ``hx-swap="outerHTML"`` +
    ``hx-select="#market-chart"`` — so this
    route returns the ``chart_region`` fragment which re-emits the SAME
    ``#market-chart`` wrapper. ``referenced=True`` marks it as htmx-only (never an
    ``<a href>``) so the orphan-route check stays quiet and the link crawl skips
    it.

    ``tf`` is clamped to :data:`feed.INTERVALS` (unknown / missing -> the default
    timeframe), so a tampered query can never reach the feed as an arbitrary
    interval. Unknown symbols 404 — the chart fragment never renders for a market
    that does not exist.
    """
    feed = get_feed()
    known = (
        feed.has_symbol(symbol)
        if hasattr(feed, "has_symbol")
        else any(m.symbol == symbol for m in feed.markets())
    )
    if not known:
        return ("Market not found", 404)

    requested = (request.query.get("tf") or "").strip()
    interval = requested if requested in INTERVALS else DEFAULT_INTERVAL
    # Same budget as the full-page hero (page.py _HERO_CANDLES) so the toggle
    # swap matches the initial paint sample density.
    closes = tuple(c.close for c in feed.candles(symbol, interval=interval, limit=64))
    return Fragment(
        _DETAIL_TEMPLATE,
        "chart_region",
        symbol=symbol,
        hero_chart=build_chart_geometry(closes, interval),
        chart_interval=interval,
        chart_intervals=INTERVALS,
    )


@app.route("/markets/{symbol}/stream", referenced=True)
def market_stream(symbol: str):
    """Live SSE for one market — ticker, order book, and trade tape.

    Iterates the feed's async ``subscribe`` stream and, per simulated tick,
    yields three OOB fragments — the detail-page regions
    ``market_ticker_oob`` / ``order_book_oob`` / ``trade_tape_oob`` (same DOM ids
    as their full-page twins, hx-swap-oob baked into the template HTML so no
    per-Fragment target is needed). The cross-page topbar strip
    (``#lucky-cat-ticker``) is intentionally NOT driven from here — it is owned
    by the global ``ticker`` SIGNAL (the /_chirp/live stream) so a single source
    updates it on every page.

    ``referenced=True`` marks the route as intentionally not linked from a
    visited page (htmx connects to it via sse-connect), so the orphan-route
    contract check stays quiet. ``worker_mode="async"`` (set on the config)
    is what lets this async generator stream.

    Cancellation-safe: when the client disconnects, the async iterator is
    cancelled and ``subscribe``'s ``CancelledError`` unwinds the generator
    cleanly. The 404 for an unknown symbol surfaces as a closed (empty) stream.
    """
    feed = get_feed()
    known = (
        feed.has_symbol(symbol)
        if hasattr(feed, "has_symbol")
        else any(m.symbol == symbol for m in feed.markets())
    )

    async def generate():
        if not known:
            return
        with contextlib.suppress(KeyError):
            async for tick in feed.subscribe(symbol):
                yield Fragment(
                    _DETAIL_TEMPLATE,
                    "market_ticker_oob",
                    symbol=symbol,
                    ticker=tick.ticker,
                )
                yield Fragment(
                    _DETAIL_TEMPLATE,
                    "order_book_oob",
                    symbol=symbol,
                    book=tick.book,
                )
                yield Fragment(
                    _DETAIL_TEMPLATE,
                    "trade_tape_oob",
                    symbol=symbol,
                    trades=tick.trades,
                )
                # NOTE: the cross-page topbar strip (#lucky-cat-ticker) is owned
                # solely by the global `ticker` SIGNAL (a single rotating spotlight
                # live on EVERY page over /_chirp/live). This per-market stream must
                # NOT also swap it — two sources innerHTML-swapping one element fight
                # and flicker. The viewed market shows in the hero #market-ticker.

    return EventStream(generate())


# ---------------------------------------------------------------------------
# CHIRP — OOB region registration
#
# The cross-page ticker strip is a `ticker` signal now (not an OOB region).
# Market-detail streams still OOB-swap market_ticker_oob / order_book_oob /
# trade_tape_oob (registered by their own templates).
# ---------------------------------------------------------------------------

# Notifications bell — the #notif-list / #notif-badge / #notif-announce sinks are
# now LIVE SIGNALS (the `notifications` source + the `notif_badge` / `notif_announce`
# derived signals), bound by MANUAL sse-swap="..." attributes on those existing
# elements in _layout.html (the signal dead-binding contract validates them). The
# old notif_badge_oob region + its OOB-region registration are gone — the badge is
# no longer an OOB twin, it is a derived-signal sink.

# Watchlist rail count badge — the layout's inner rail always renders the
# #watchlist-count element on the Markets room, so a missing block is an honest
# ERROR (non-optional). The /watchlist/toggle route re-renders this region as an
# innerHTML OOB swap (same #watchlist-count id). Ticker/balance/bell chrome use
# signals instead of OOB regions.
# wrap=False: the count twin (watchlist_count_swap) bakes its OWN
# #watchlist-count wrapper + hx-swap-oob, so the OOB framework must emit it
# verbatim rather than double-wrapping it.
app.register_oob_region(
    "watchlist_count_oob", target_id="watchlist-count", swap="innerHTML", wrap=False
)

# ---------------------------------------------------------------------------
# CHIRP — mount filesystem pages LAST
# ---------------------------------------------------------------------------

app.mount_pages(str(PAGES_DIR))

if __name__ == "__main__":
    app.run()
