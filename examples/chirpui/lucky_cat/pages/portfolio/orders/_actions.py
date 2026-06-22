"""Actions for /portfolio/orders — cancel resting limit orders."""

import trade_store
from pages.trade._trade_helpers import (
    open_order_count_fragment,
    orders_table_empty_fragment,
    toast,
)

from chirp import FormAction, login_required
from chirp.pages.actions import action


@action("cancel")
@login_required
def cancel_order(order_id=""):
    try:
        oid = int(order_id)
    except ValueError, TypeError:
        oid = -1
    cancelled = trade_store.cancel_order(oid)
    message = "Order cancelled." if cancelled is not None else "Order not found."
    variant = "info" if cancelled is not None else "warning"
    fragments = [open_order_count_fragment()]
    if trade_store.open_order_count() == 0:
        fragments.append(orders_table_empty_fragment())
    return FormAction(
        "/trade",
        *fragments,
        toast(message, variant=variant),
        trigger="orderCancelled",
    )
