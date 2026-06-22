"""Live signal registration — must run before mount_pages. DESIGN.md §7."""
import asyncio
import contextlib
import time

import lobby
import notifications
import session_store
from feed import get_feed

from chirp import Fragment

from wiring.app_factory import app, fan_out_notifications_live, emit_signal

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


# CHIRP — DESIGN.md

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


# Notifications — DESIGN.md

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


# CHIRP — DESIGN.md


