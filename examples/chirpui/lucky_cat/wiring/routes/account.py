"""Shell-global account routes — POST /logout."""

from chirp import FormAction, logout

from wiring.app_factory import app


def register(app_instance) -> None:
    @app_instance.route("/logout", methods=["POST"], name="logout")
    def do_logout():
        logout()
        return FormAction("/")
