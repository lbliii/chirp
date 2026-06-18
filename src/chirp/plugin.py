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

Fail-soft at boot
~~~~~~~~~~~~~~~~~

If a plugin's ``register()`` *raises*, ``app.mount`` **quarantines** it: the
exception is caught, the plugin is skipped, and the app keeps booting so one
broken plugin cannot abort startup. The quarantine is never silent — a WARNING
is logged at mount time and ``app.check()`` reports it as an ERROR in category
``plugin_quarantine`` (deploy-blocking under ``chirp check --deploy``). A plugin
that registers some routes before raising leaves that partial state behind;
quarantine does not roll it back. Passing a non-plugin object (no callable
``register``) is a programmer error and stays fail-loud with
``ConfigurationError``.

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
