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

Contract checks
~~~~~~~~~~~~~~~

Plugins that ship custom contract validation rules should register them
inside their ``register()`` method using ``app.register_contract_check()``.
This keeps discovery explicit — no magic entry-points or auto-import.

Example::

    class BlogPlugin:
        def register(self, app: App, prefix: str) -> None:
            app.register_contract_check(check_blog_templates)
            ...

    def check_blog_templates(snapshot, result):
        for name, source in snapshot.template_sources.items():
            if name.startswith("blog/") and "{% block title %}" not in source:
                result.issues.append(ContractIssue(
                    severity=Severity.WARNING,
                    category="blog",
                    message=f"Blog template missing title block",
                    template=name,
                ))

See ``chirp.ext.chirp_ui`` for a real-world example.
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
