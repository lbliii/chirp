"""Actions for /markets — deposit (topbar modal posts here)."""

import notifications
from wallet import deposit as credit_meow

from chirp import login_required
from chirp.pages.actions import action
from chirp.templating.returns import SignalEmit


@action("deposit")
@login_required
async def deposit(amount=""):
    try:
        parsed = int(amount)
    except ValueError, TypeError:
        parsed = 0
    new_balance = credit_meow(parsed)
    credit = max(0, parsed)
    emits: list[tuple[str, object]] = [("balance", new_balance)]
    if credit > 0:
        notifications.add(
            "deposit",
            f"Deposited {credit} $MEOW",
            f"Balance now {new_balance} $MEOW.",
        )
        emits.append(("notifications", notifications.snapshot()))
    return SignalEmit(*emits)
