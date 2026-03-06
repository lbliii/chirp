"""Root page for the contacts shell example."""

from chirp import Redirect


def get() -> Redirect:
    return Redirect("/contacts")
