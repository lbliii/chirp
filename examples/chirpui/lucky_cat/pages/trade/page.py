"""Trade room — GET /trade (#225 place/cancel-order flow).

Renders the place-order form plus the live positions table and open-order
count. The form POSTs to ``/trade/order`` (registered in ``app.py`` before
``mount_pages``); on a fill the route returns a single ``FormAction`` that
OOB-swaps the positions table, the topbar $MEOW balance, the open-order count
badge, and a toast — htmx gets the fragments, a plain POST gets a 303 redirect
back to ``/trade``.

``markets`` flows in from the root ``_context.py`` (the form's symbol select);
``positions`` / ``open_order_count`` come from the thread-safe ``trade_store``.
"""

import trade_store

from chirp import Page


def get() -> Page:
    return Page(
        "trade/page.html",
        "page_content",
        page_block_name="page_root",
        positions=trade_store.positions(),
        open_order_count=trade_store.open_order_count(),
    )
