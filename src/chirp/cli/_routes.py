"""``chirp routes`` — list registered routes.

Resolves an import string to a chirp App and prints all registered
routes with method, path, and handler info.
"""

import argparse
import sys

from chirp.cli._resolve import resolve_app


def run_routes(args: argparse.Namespace) -> None:
    """List registered routes for a chirp app.

    Resolves ``args.app`` to an App instance, freezes it, and prints
    a table of METHOD, PATH, and handler name.
    """
    try:
        app = resolve_app(args.app)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    app._ensure_frozen()
    router = app._router
    if router is None:
        print("No routes registered.", file=sys.stderr)
        raise SystemExit(1)

    routes = router.routes
    if not routes:
        print("No routes registered.")
        return

    # Build rows: (methods_str, path, handler_name)
    rows: list[tuple[str, str, str]] = []
    for route in routes:
        methods_str = ", ".join(sorted(route.methods))
        handler_name = getattr(route.handler, "__name__", str(route.handler))
        if route.name:
            handler_name = f"{handler_name} ({route.name})"
        rows.append((methods_str, route.path, handler_name))

    # Column widths
    max_methods = max(len(r[0]) for r in rows)
    max_path = max(len(r[1]) for r in rows)
    max_methods = max(max_methods, 6)  # "METHOD" header
    max_path = max(max_path, 4)  # "PATH" header

    # Print table
    fmt = f"{{:<{max_methods}}}  {{:<{max_path}}}  {{}}"
    print(fmt.format("METHOD", "PATH", "HANDLER"))
    sep_len = max_methods + max_path + 4 + max((len(r[2]) for r in rows), default=0)
    print("-" * min(sep_len, 80))
    for methods_str, path, handler_name in rows:
        print(fmt.format(methods_str, path, handler_name))
