"""Activity room — GET /activity (the merged feed).

The Activity landing is the room's *combined* stream: every wallet deposit
(``wallet.deposits()``) and every trade fill (``trade_store.history()``)
interleaved by timestamp, newest first — the same records the two sub-pages
(``/activity/deposits`` + ``/activity/trades``) show split out by kind. It
reuses the sub-pages' row language (the dense ``.luckycat-fills`` table: a
leading mono time column, a jade/red directional side pill, right-aligned Geist
Mono figures), with a deposit row and a fill row that read distinctly.

Each row is a plain view-model dict (so the template emits only strings — no
model coupling, mirroring the deposits/trades page.py): ``kind`` is "deposit" or
"fill" and keys the row markup; ``ts`` is kept only for the merge sort. The
polished maneki empty state shows ONLY when BOTH sources are empty.
"""

import time

import trade_store
import wallet

from chirp import Page, login_required

_TIME_FMT = "%H:%M:%S"


def _merged_rows() -> tuple[dict[str, object], ...]:
    """Deposits + fills interleaved by ``ts``, newest first.

    Both ``wallet.deposits()`` and ``trade_store.history()`` already come back
    newest-first; merging them on each record's ``ts`` keeps the combined feed
    in true reverse-chronological order regardless of which source is busier.
    """
    deposit_rows: list[dict[str, object]] = [
        {
            "kind": "deposit",
            "ts": d.ts,
            "when": time.strftime(_TIME_FMT, time.localtime(d.ts)),
            "amount": d.amount,
            "balance_after": d.balance_after,
        }
        for d in wallet.deposits()
    ]
    fill_rows: list[dict[str, object]] = [
        {
            "kind": "fill",
            "ts": f.ts,
            "when": time.strftime(_TIME_FMT, time.localtime(f.ts)),
            "symbol": f.symbol,
            "side": f.side,
            "size": f.size,
            "price": f.price,
            "notional": round(f.size * f.price, 2),
        }
        for f in trade_store.history()
    ]
    rows = deposit_rows + fill_rows
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return tuple(rows)


@login_required
def get() -> Page:
    return Page(
        "activity/page.html",
        "page_content",
        page_block_name="page_root",
        rows=_merged_rows(),
    )
