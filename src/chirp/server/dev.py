"""Development server with hot reload.

Starts a pounce ASGI server with the live chirp App object.
Uses single-worker mode with reload enabled for development.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def run_dev_server(
    app: object,
    host: str,
    port: int,
    *,
    reload: bool = True,
    reload_include: tuple[str, ...] = (),
    reload_dirs: tuple[str, ...] = (),
    app_path: str | None = None,
    lifecycle_collector: object | None = None,
) -> None:
    """Start a pounce dev server with the given chirp App.

    Pounce's ``run()`` takes an import string (e.g., ``"myapp:app"``),
    but chirp has a live ``App`` object. We use ``pounce.Server``
    directly with the ASGI callable.

    Args:
        app: ASGI callable (chirp App instance).
        host: Bind host address.
        port: Bind port number.
        reload: Enable auto-reload on file changes (default True).
        reload_include: Extra file extensions to watch when reload is
            active (e.g. ``(".html", ".css", ".md")``).
        reload_dirs: Extra directories to watch alongside cwd.
        app_path: Optional ``"module:attribute"`` import string.  When
            provided, pounce reimports the app on each reload cycle so
            that code changes on disk take effect immediately.
        lifecycle_collector: Optional Pounce LifecycleCollector for
            observability.  Forwarded to the Pounce Server.
    """
    from pounce.config import ServerConfig
    from pounce.server import Server

    config = ServerConfig(
        host=host,
        port=port,
        workers=1,
        reload=reload,
        reload_include=reload_include,
        reload_dirs=reload_dirs,
    )
    server = Server(
        config, app, app_path=app_path, lifecycle_collector=lifecycle_collector,
    )
    server.run()
