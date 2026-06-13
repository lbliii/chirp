"""Portfolio → Open orders — GET /portfolio/orders.

Lists the resting limit orders booked by the #225 trade flow
(``trade_store.open_orders()``), with a Cancel control per row that posts to the
existing ``trade.cancel`` route. Renders into the chirp-ui shell content block
(``page_root`` → ``page_content``), so the two-tier rail keeps Portfolio active
and the inner rail's "Open orders" lane lit (navigation.py emits the
``/portfolio/orders`` href + ``portfolio_active`` prefix).

Each row's Cancel form posts to ``/trade/order/{id}/cancel`` (already registered
in app.py). It does a *local* htmx swap: the inherited boosted-shell outlet
attrs (``hx-target=#main`` / ``hx-swap=innerHTML`` / ``hx-select=#page-content``)
are overridden on the form so the only DOM change is the row deleting itself
(``hx-target="closest tr" hx-swap="delete"``). The cancel route's FormAction
still OOB-swaps the ``#open-order-count`` badge (which this page renders) and a
toast, so the count stays honest without a full-page round trip.
"""

import time

import trade_store

from chirp import Page

# The template only renders strings, so format the wall-clock placement time
# here (no datetime-filter assumptions in the template), mirroring the history
# view's view-model shape.
_TIME_FMT = "%H:%M:%S"


def _rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "id": o.id,
            "symbol": o.symbol,
            "side": o.side,
            "size": o.size,
            "limit_price": o.limit_price,
            "when": time.strftime(_TIME_FMT, time.localtime(o.ts)),
        }
        for o in trade_store.open_orders()
    )


def get() -> Page:
    return Page(
        "portfolio/orders/page.html",
        "page_content",
        page_block_name="page_root",
        orders=_rows(),
    )
