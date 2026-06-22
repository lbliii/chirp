"""Actions for /markets — deposit (topbar modal posts here)."""

import notifications
from wallet import deposit as credit_meow
from wiring.app_factory import emit_signal

from chirp import login_required
from chirp.pages.actions import action


@action("deposit")
@login_required
async def deposit(amount=""):
    try:
        parsed = int(amount)
    except ValueError, TypeError:
        parsed = 0
    new_balance = credit_meow(parsed)
    emit_signal("balance", new_balance)
    credit = max(0, parsed)
    if credit > 0:
        notifications.add(
            "deposit",
            f"Deposited {credit} $MEOW",
            f"Balance now {new_balance} $MEOW.",
        )
        emit_signal("notifications", notifications.snapshot())
    return ("", 204)
