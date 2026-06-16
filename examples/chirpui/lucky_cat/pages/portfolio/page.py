"""Portfolio room — GET /portfolio (Suspense dashboard).

Minimal Suspense idiom (learn this first)::

    return Suspense(
        "portfolio/page.html",
        title="Portfolio",
        value=_load_value(),      # awaitable → DEFERRED in shell, streamed as OOB
        holdings=_load_holdings(),
    )

This page is the **advanced** version: six deferred panels, explicit
``defer_blocks`` (several keys appear only inside chirp-ui macro args where static
discovery cannot see them), and ``defer_map`` (block names whose DOM section ids
use hyphens or different suffixes). Auth and CSRF in the streamed shell are
handled by the framework — no handler-side capture needed.

Deferred keys map to template blocks; each resolves from the thread-safe
``trade_store`` via ``asyncio.to_thread`` so the value is a genuine awaitable.
Use ``{% if key is deferred %}`` in templates for skeleton vs loaded — not bare
``{% if key %}`` (empty tuple/list resolves falsy after load).

The free-threading proof panel (sync facts in the shell + ``/ft/stream`` SSE for
live ticks/sec) ships alongside the Suspense panels.
"""

import asyncio

import trade_store
from feed import get_feed

from chirp import Suspense, login_required


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
    """Sync free-threading facts for the shell. Honest: default 3.14 reports
    ``GIL: enabled``; a 3.14t deploy flips it to ``disabled``. Live ticks/sec
    arrives over ``/ft/stream``."""
    import sys

    feed = get_feed()
    gil_enabled = sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True
    return {
        "ft_gil_enabled": gil_enabled,
        "ft_workers": getattr(feed, "worker_count", 0),
        "ft_markets": getattr(feed, "market_count", len(feed.markets())),
        "ft_ticks_per_sec": None,  # filled live by the /ft/stream SSE twin
    }


@login_required
def get() -> Suspense:
    return Suspense(
        "portfolio/page.html",
        defer_blocks=(
            "portfolio_value",
            "holdings",
            "allocation",
            "open_orders",
            "activity",
        ),
        defer_map={
            "portfolio_value": "portfolio-value",
            "open_orders": "open-orders",
            "activity": "activity-feed",
        },
        title="Portfolio",
        value=_load_value(),
        pnl=_load_pnl(),
        holdings=_load_holdings(),
        allocation=_load_allocation(),
        open_orders=_load_open_orders(),
        activity=_load_activity(),
        **_ft_panel_context(),
    )
