"""Shared trade mutation helpers — toast + OOB fragments for _actions handlers."""

import trade_store

from chirp import Fragment

_TRADE_TEMPLATE = "trade/page.html"
_TOAST_TEMPLATE = "_components/toast_oob.html"
_ORDERS_TEMPLATE = "portfolio/orders/page.html"


def toast(message: str, variant: str = "success") -> Fragment:
    return Fragment(_TOAST_TEMPLATE, "toast", message=message, variant=variant)


def fill_fragments() -> tuple[Fragment, ...]:
    return (
        Fragment(_TRADE_TEMPLATE, "positions_oob", positions=trade_store.positions()),
        Fragment(
            _TRADE_TEMPLATE,
            "open_order_count_oob",
            open_order_count=trade_store.open_order_count(),
        ),
    )


def open_order_count_fragment() -> Fragment:
    return Fragment(
        _TRADE_TEMPLATE,
        "open_order_count_oob",
        open_order_count=trade_store.open_order_count(),
    )


def orders_table_empty_fragment() -> Fragment:
    return Fragment(_ORDERS_TEMPLATE, "orders_table_oob", orders=())
