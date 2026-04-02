"""Plugin protocol — structural typing for reusable Chirp plugins.

A plugin is any object with a ``register(app, prefix)`` method.
No base class required.

Usage (plugin author)::

    class BlogPlugin:
        def register(self, app: App, prefix: str) -> None:
            @app.route(f"{prefix}/")
            async def blog_index():
                return Template("blog/index.html")

Usage (plugin consumer)::

    app = App()
    app.mount("/blog", BlogPlugin())
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chirp.app import App


__all__ = ["ChirpPlugin"]


class ChirpPlugin(Protocol):
    """Protocol for Chirp plugins.

    Any object with a ``register`` method matching this signature
    is a valid plugin — no inheritance required.
    """

    def register(self, app: App, prefix: str) -> None: ...
