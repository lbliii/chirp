"""Actions for /trade — place order (POST-to-self via _action=order)."""

import notifications
import trade_store
from feed import get_feed
from pages.trade._trade_helpers import fill_fragments, open_order_count_fragment, toast
from wallet import balance as meow_balance
from wiring.app_factory import emit_signal

from chirp import FormAction, Fragment, ValidationError, login_required
from chirp.pages.actions import action

_TRADE_TEMPLATE = "trade/page.html"


@action("order")
@login_required
async def place_order(
    symbol="",
    side="buy",
    kind="market",
    size="",
    limit_price="",
):
    feed = get_feed()
    markets = feed.markets()
    values = {
        "symbol": (symbol or "").strip(),
        "side": (side or "buy").strip(),
        "kind": (kind or "market").strip(),
        "size": (size or "").strip(),
        "limit_price": (limit_price or "").strip(),
    }

    errors, parsed = trade_store.validate_order(
        values["symbol"],
        values["side"],
        values["kind"],
        values["size"],
        values["limit_price"],
    )
    if errors:
        return ValidationError(
            _TRADE_TEMPLATE,
            "order_form",
            errors=errors,
            form=values,
            markets=markets,
        )

    if values["kind"] == "limit":
        resting = trade_store.open_limit_order(
            values["symbol"],
            values["side"],
            parsed["size"],
            parsed["limit_price"],
        )
        return FormAction(
            "/trade",
            Fragment(_TRADE_TEMPLATE, "order_form", markets=markets, form={}, errors=None),
            open_order_count_fragment(),
            toast(
                f"Resting {resting.side} {resting.size:g} {resting.symbol} "
                f"@ {resting.limit_price:g}.",
                variant="info",
            ),
            trigger="orderResting",
        )

    order, fill_errors = trade_store.try_place_order(
        values["symbol"],
        values["side"],
        values["kind"],
        parsed["size"],
        parsed["limit_price"],
        fill_price=parsed["fill_price"],
    )
    if order is None:
        return ValidationError(
            _TRADE_TEMPLATE,
            "order_form",
            errors=fill_errors,
            form=values,
            markets=markets,
        )

    notifications.add(
        "fill",
        f"Filled {order.side} {order.size:g} {order.symbol}",
        f"@ {order.size * parsed['fill_price']:g} $MEOW.",
    )
    emit_signal("notifications", notifications.snapshot())
    emit_signal("balance", meow_balance())
    return FormAction(
        "/trade",
        Fragment(_TRADE_TEMPLATE, "order_form", markets=markets, form={}, errors=None),
        *fill_fragments(),
        toast(f"Filled {order.side} {order.size:g} {order.symbol}.", variant="success"),
        trigger="orderFilled",
    )
