"""Activity → Deposits — GET /activity/deposits.

The deposit-side activity view. The wallet now keeps an append-only deposit
ledger (``wallet.deposits()`` — every topbar Deposit credit, newest first), so
this view shows the live $MEOW balance as the hero figure plus the statement of
credits beneath it. Renders into the chirp-ui shell content block; navigation.py
keeps Activity active and lights the inner rail's "Deposits" lane
(``/activity/deposits`` href + ``activity_active`` prefix).
"""

import time

import wallet

from chirp import Page

_TIME_FMT = "%H:%M:%S"


def _rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "amount": d.amount,
            "balance_after": d.balance_after,
            "when": time.strftime(_TIME_FMT, time.localtime(d.ts)),
        }
        for d in wallet.deposits()
    )


def get() -> Page:
    return Page(
        "activity/deposits/page.html",
        "page_content",
        page_block_name="page_root",
        meow_balance=wallet.balance(),
        deposits=_rows(),
    )
