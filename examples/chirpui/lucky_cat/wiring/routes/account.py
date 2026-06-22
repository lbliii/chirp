"""Shell-global account routes — POST /logout."""

from chirp import FormAction, logout


def register(app_instance) -> None:
    @app_instance.route("/logout", methods=["POST"], name="logout")
    def do_logout():
        logout()
        return FormAction("/")
