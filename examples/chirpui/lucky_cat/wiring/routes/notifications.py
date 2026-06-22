"""Notifications bell — POST /notifications/read (layout-global)."""

import notifications

from chirp import login_required
from chirp.templating.returns import SignalEmit


def register(app_instance) -> None:
    @app_instance.route("/notifications/read", methods=["POST"], name="notifications.read")
    @login_required
    def notifications_read():
        notifications.mark_all_read()
        return SignalEmit(("notifications", notifications.snapshot()))
