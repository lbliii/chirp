"""Activity → Trades — GET /activity/trades.

The trade-side activity stream: the fill log from ``trade_store.history()``,
newest first (the same data the portfolio History view shows, framed as the
"trades" activity filter and rendered through the shared fills_table macro).
Renders into the chirp-ui shell content block; navigation.py keeps Activity
active and lights the inner rail's "Trades" lane (``/activity/trades`` href +
``activity_active`` prefix).
"""

import time

import trade_store

from chirp import Page, login_required

_TIME_FMT = "%H:%M:%S"


def _rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "symbol": f.symbol,
            "side": f.side,
            "size": f.size,
            "price": f.price,
            "notional": round(f.size * f.price, 2),
            "when": time.strftime(_TIME_FMT, time.localtime(f.ts)),
        }
        for f in trade_store.history()
    )


@login_required
def get() -> Page:
    return Page(
        "activity/trades/page.html",
        "page_content",
        page_block_name="page_root",
        fills=_rows(),
    )
