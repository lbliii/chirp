"""Portfolio → History — GET /portfolio/history.

The fill log (``trade_store.history()``), newest first. Renders into the chirp-ui
shell content block; navigation.py keeps Portfolio active and lights the inner
rail's "History" lane (``/portfolio/history`` href + ``portfolio_active`` prefix).

Fills carry an epoch ``ts``; the wall-clock time is formatted into a string here
so the template only renders strings (no datetime-filter assumptions), and the
notional ($MEOW) is precomputed for the figure column.
"""

import time

import trade_store

from chirp import Page

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


def get() -> Page:
    return Page(
        "portfolio/history/page.html",
        "page_content",
        page_block_name="page_root",
        fills=_rows(),
    )
