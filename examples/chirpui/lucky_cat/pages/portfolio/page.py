"""Portfolio room — GET /portfolio (#224 Suspense dashboard, #227 FT panel).

The portfolio is the example's Suspense surface: the shell paints instantly
(skeletons in every panel), then six deferred panels stream in as OOB swaps as
their awaitable context resolves from the thread-safe ``trade_store`` —

* ``value``       — portfolio mark-to-market value ($MEOW cash + positions)
* ``pnl``         — unrealized profit/loss
* ``holdings``    — open positions table (empty tuple → empty state, NOT a stuck
                    skeleton — the ``is deferred`` correctness proof)
* ``allocation``  — per-symbol % of portfolio value (derived in the loader)
* ``open_orders`` — resting limit orders + the live ``#open-order-count`` badge
* ``activity``    — recent fills (trade history)

Each store read is sync and cheap, but we wrap it in ``asyncio.to_thread`` so the
value is a genuine awaitable — that is what makes :class:`~chirp.Suspense` defer
it (replace it with the ``DEFERRED`` sentinel in the shell) and stream the real
markup as an OOB swap once it resolves. Mounted ``Suspense`` is upgraded to a
``LayoutSuspense`` automatically, so the shell composes inside ``_layout.html``.

``defer_blocks`` is passed explicitly to bypass static block discovery: several
deferred keys are only referenced inside chirp-ui macro args (``skeleton`` /
``metric``) where the analyzer cannot see them, so we name every deferred block
directly. ``defer_map`` remaps every block whose DOM id differs from the block
name — the deferred OOB swap targets the block's *section* id, so a block left
un-remapped emits an OOB wrapper id that matches no DOM element and the swap is
silently dropped (``portfolio_value`` → ``portfolio-value``, ``open_orders`` →
``open-orders``, ``activity`` → ``activity-feed``).

#227 Part A: the free-threading proof panel ships in the shell with the GIL
state + parallel-work width (sync, no defer), and a small SSE route
(``/ft/stream``) swaps a live ticks/sec figure into ``#ft-panel`` as the engine
fans ticks across the worker pool.
"""

import asyncio

import trade_store
from feed import get_feed

from chirp import Suspense


async def _load_value() -> float:
    return await asyncio.to_thread(trade_store.portfolio_value)


async def _load_pnl() -> float:
    return await asyncio.to_thread(trade_store.pnl)


async def _load_holdings() -> tuple:
    return await asyncio.to_thread(trade_store.positions)


async def _load_open_orders() -> tuple:
    return await asyncio.to_thread(trade_store.open_orders)


async def _load_activity() -> tuple:
    return await asyncio.to_thread(trade_store.history)


async def _load_allocation() -> tuple[dict, ...]:
    """Per-symbol share of portfolio value, descending. Derived off a single
    consistent snapshot so the percentages sum coherently."""

    def compute() -> tuple[dict, ...]:
        feed = get_feed()
        held = trade_store.positions()
        total = trade_store.portfolio_value()
        rows: list[dict] = []
        for p in held:
            mark = feed.ticker(p.symbol).price
            mkt_value = p.size * mark
            pct = (mkt_value / total * 100.0) if total else 0.0
            rows.append(
                {
                    "symbol": p.symbol,
                    "value": round(mkt_value, 2),
                    "pct": round(pct, 1),
                }
            )
        rows.sort(key=lambda r: r["value"], reverse=True)
        return tuple(rows)

    return await asyncio.to_thread(compute)


def _ft_panel_context() -> dict:
    """Sync free-threading facts for the shell (#227 Part A). Honest: this build
    reports ``GIL: enabled`` on a default 3.14; a 3.14t deploy flips it to
    ``disabled``. The live ticks/sec figure arrives over ``/ft/stream``."""
    import sys

    feed = get_feed()
    gil_enabled = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
    return {
        "ft_gil_enabled": gil_enabled,
        "ft_workers": getattr(feed, "worker_count", 0),
        "ft_markets": getattr(feed, "market_count", len(feed.markets())),
        "ft_ticks_per_sec": None,  # filled live by the /ft/stream SSE twin
    }


def _captured_csrf() -> dict:
    """Capture the request's CSRF token so the streamed Suspense shell can render
    the chirp-ui ``<meta name="csrf-token">`` tag.

    The chirp-ui app-shell head calls the ``csrf_token()`` template global, which
    reads a request-scoped ContextVar. Suspense renders its shell *after* the
    request middleware stack unwinds (the stream body runs lazily), by which point
    ``CSRFMiddleware`` has reset that ContextVar — so the global raises K-RUN-007.
    The framework's prescribed fix is to capture the raw token in the handler
    (where the ContextVar is still live) and pass it into the template context. A
    context value shadows the same-named global, so ``csrf_token()`` resolves to
    the captured value during the deferred render. Returns an empty dict if CSRF
    is not active (keeps the page renderable without the secure stack)."""
    try:
        from chirp.middleware.csrf import get_csrf_token

        token = get_csrf_token()
    except LookupError, ImportError:
        return {}
    return {"csrf_token": lambda t=token: t}


def get() -> Suspense:
    return Suspense(
        "portfolio/page.html",
        # Bypass static discovery — several deferred keys appear only inside
        # chirp-ui macro args, which the analyzer cannot trace.
        defer_blocks=(
            "portfolio_value",
            "holdings",
            "allocation",
            "open_orders",
            "activity",
        ),
        # Remap every block whose DOM id ≠ block name. The OOB swap targets the
        # block's *section* id, so each block name must map to its section id —
        # an un-remapped block emits an OOB wrapper id that matches no DOM element
        # and htmx silently drops the swap (the panel stays a skeleton forever).
        # portfolio_value→portfolio-value and open_orders→open-orders carry the
        # underscore→hyphen rename; activity→activity-feed is a full rename.
        defer_map={
            "portfolio_value": "portfolio-value",
            "open_orders": "open-orders",
            "activity": "activity-feed",
        },
        title="Portfolio",
        # Deferred (awaitable → DEFERRED sentinel in the shell, streamed as OOB).
        value=_load_value(),
        pnl=_load_pnl(),
        holdings=_load_holdings(),
        allocation=_load_allocation(),
        open_orders=_load_open_orders(),
        activity=_load_activity(),
        # Sync free-threading facts live in the shell (#227 Part A).
        **_ft_panel_context(),
        # Capture the CSRF token so the streamed shell's chirp-ui csrf-meta tag
        # renders (the ContextVar is reset before the deferred render runs).
        **_captured_csrf(),
    )
