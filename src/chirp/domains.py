"""Domain protocol for pluggable feature modules.

Domains register routes, middleware, and other app extensions on first access.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chirp import App


class Domain(Protocol):
    """Protocol for pluggable domain modules.

    A domain encapsulates a feature (e.g. admin, API, docs) and
    registers its routes and middleware with the app when invoked.
    """

    def register(self, app: App) -> None:
        """Register routes, middleware, and other extensions with the app."""
        ...
