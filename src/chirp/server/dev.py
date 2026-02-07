"""Development server with hot reload.

Starts a pounce ASGI server with the live chirp App object.
Uses single-worker mode with reload enabled for development.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp._internal.asgi import Receive, Scope, Send


def run_dev_server(
    app: object,
    host: str,
    port: int,
    *,
    reload: bool = True,
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
    """
    from pounce.config import ServerConfig
    from pounce.server import Server

    config = ServerConfig(
        host=host,
        port=port,
        workers=1,
        reload=reload,
    )
    server = Server(config, app)
    server.run()
