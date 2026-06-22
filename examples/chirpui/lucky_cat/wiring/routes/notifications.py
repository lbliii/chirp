"""Notifications bell — POST /notifications/read (layout-global)."""

import notifications

from chirp import login_required

from wiring.app_factory import app, emit_signal


def register(app_instance) -> None:
    @app_instance.route("/notifications/read", methods=["POST"], name="notifications.read")
    @login_required
    def notifications_read():
        notifications.mark_all_read()
        emit_signal("notifications", notifications.snapshot())
        return ("", 204)
