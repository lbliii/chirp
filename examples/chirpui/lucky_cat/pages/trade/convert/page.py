"""Trade → Convert — GET /trade/convert.

A simplified "convert" affordance: pick a market and a size, and convert $MEOW
into it. Rather than introduce a second mutating route, the form reuses the #225
``trade.order`` route as a plain (non-htmx) market buy — so a submit fills via
the existing thread-safe ``try_place_order`` path and gets the FormAction 303
redirect back to /trade. Renders into the chirp-ui shell content block;
navigation.py keeps Trade active and lights the inner rail's "Convert" lane
(``/trade/convert`` href + ``trade_active`` prefix).

``markets`` flows in from the root _context.py (the convert select).
"""

import trade_store

from chirp import Page, Request, login_required


@login_required
def get() -> Page:
    return Page(
        "trade/convert/page.html",
        "page_content",
        page_block_name="page_root",
        positions=trade_store.positions(),
    )


@login_required
async def post(request: Request) -> Page:
    """Fallback — convert dispatches via ``pages/trade/convert/_actions.py``."""
    return get()
