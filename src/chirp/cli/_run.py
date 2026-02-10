"""``chirp run`` — development server command.

Resolves an import string to a chirp App and starts the pounce dev
server with optional host/port overrides.
"""

import argparse
import sys

from chirp.cli._resolve import resolve_app


def run_server(args: argparse.Namespace) -> None:
    """Start the chirp development server.

    Resolves ``args.app`` to a chirp App, then delegates to
    ``run_dev_server()`` with the resolved app and CLI overrides
    for host/port.  The original import string is forwarded as
    ``app_path`` so pounce can reimport on reload.
    """
    try:
        app = resolve_app(args.app)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    from chirp.server.dev import run_dev_server

    host = args.host or app.config.host
    port = args.port or app.config.port

    run_dev_server(
        app,
        host,
        port,
        reload=app.config.debug,
        reload_include=app.config.reload_include,
        reload_dirs=app.config.reload_dirs,
        app_path=args.app,
    )
