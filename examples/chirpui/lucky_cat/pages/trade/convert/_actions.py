"""Actions for /trade/convert — market-buy convert flow."""

import trade_store
from feed import get_feed
from pages.trade._trade_helpers import toast
from wallet import balance as meow_balance
from wiring.app_factory import emit_signal

from chirp import FormAction, Fragment, Request, login_required
from chirp.pages.actions import action


@action("convert")
@login_required
async def convert_order(request: Request, symbol="", size=""):
    feed = get_feed()
    markets = feed.markets()
    values = {"symbol": (symbol or "").strip(), "size": (size or "").strip()}

    errors, parsed = trade_store.validate_order(
        values["symbol"], "buy", "market", values["size"], ""
    )
    if not errors:
        order, fill_errors = trade_store.try_place_order(
            values["symbol"],
            "buy",
            "market",
            parsed["size"],
            parsed["limit_price"],
            fill_price=parsed["fill_price"],
        )
        if order is None:
            errors = fill_errors

    if errors:
        if request.headers.get("HX-Request") == "true":
            return Fragment(
                "trade/convert/page.html",
                "convert_form",
                errors=errors,
                form=values,
                markets=markets,
            )
        return FormAction("/trade/convert")

    emit_signal("balance", meow_balance())
    return FormAction(
        "/trade",
        Fragment("trade/convert/page.html", "convert_form", markets=markets, errors=None, form={}),
        toast(f"Converted {parsed['size']:g} $MEOW into {values['symbol']}.", variant="success"),
        trigger="orderFilled",
    )
