"""Trade room — GET /trade (#225 place/cancel-order flow).

Renders the place-order form plus the live positions table and open-order
count. The form POSTs to ``/trade`` with ``_action=order`` (``pages/trade/_actions.py``);
on a fill the action returns a ``FormAction`` that OOB-swaps the positions table,
the topbar $MEOW balance, the open-order count badge, and a toast.

``markets`` flows in from the root ``_context.py`` (the form's symbol select);
``positions`` / ``open_order_count`` come from the thread-safe ``trade_store``.
"""

import trade_store

from chirp import Page, Request, login_required


@login_required
def get() -> Page:
    return Page(
        "trade/page.html",
        "page_content",
        page_block_name="page_root",
        positions=trade_store.positions(),
        open_order_count=trade_store.open_order_count(),
    )


@login_required
async def post(request: Request) -> Page:
    """Fallback — place order dispatches via ``pages/trade/_actions.py``."""
    return get()
