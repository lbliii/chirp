"""``chirp routes`` — list registered routes.

Resolves an import string to a chirp App and prints all registered
routes with method, path, and handler info.
"""

import argparse
from typing import Any

from chirp.cli._inspection import (
    InspectionResult,
    emit_terminal_result,
    resolution_error,
)
from chirp.cli._resolve import resolve_app


def run_routes(args: argparse.Namespace) -> None:
    """List registered routes for a chirp app.

    Resolves ``args.app`` to an App instance, freezes it, and prints
    a table of METHOD, PATH, and handler name.
    """
    emit_terminal_result(collect_routes_result(args.app))


def collect_routes_result(app_import: str) -> InspectionResult:
    """Return the frozen route table as stable structured data."""
    try:
        app = resolve_app(app_import)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        return resolution_error(app_import, exc)

    app._ensure_frozen()
    router = app._router
    if router is None:
        return InspectionResult(
            {
                "ok": False,
                "error": {
                    "code": "CHIRP_ROUTER_MISSING",
                    "message": "No routes registered.",
                    "suggestion": "Register at least one route before inspecting the app.",
                    "app_import": app_import,
                },
            },
            terminal_text="No routes registered.",
            exit_code=1,
            terminal_stream="stderr",
        )

    routes = router.routes
    if not routes:
        return InspectionResult(
            {"app_import": app_import, "routes": []},
            terminal_text="No routes registered.",
        )

    rows: list[dict[str, Any]] = []
    for route in routes:
        methods = sorted(route.methods)
        handler_name = getattr(route.handler, "__name__", str(route.handler))
        if route.name:
            handler_name = f"{handler_name} ({route.name})"
        rows.append(
            {
                "methods": methods,
                "path": route.path,
                "handler": handler_name,
                "name": route.name,
            }
        )

    return InspectionResult(
        {"app_import": app_import, "routes": rows},
        terminal_text=_format_route_table(rows),
    )


def _format_route_table(rows: list[dict[str, Any]]) -> str:
    """Format structured route rows using the established CLI table."""
    terminal_rows = [
        (", ".join(row["methods"]), str(row["path"]), str(row["handler"])) for row in rows
    ]

    # Column widths
    max_methods = max(len(r[0]) for r in terminal_rows)
    max_path = max(len(r[1]) for r in terminal_rows)
    max_methods = max(max_methods, 6)  # "METHOD" header
    max_path = max(max_path, 4)  # "PATH" header

    # Print table
    fmt = f"{{:<{max_methods}}}  {{:<{max_path}}}  {{}}"
    lines = [fmt.format("METHOD", "PATH", "HANDLER")]
    sep_len = max_methods + max_path + 4 + max((len(r[2]) for r in terminal_rows), default=0)
    lines.append("-" * min(sep_len, 80))
    lines.extend(fmt.format(methods, path, handler) for methods, path, handler in terminal_rows)
    return "\n".join(lines)
