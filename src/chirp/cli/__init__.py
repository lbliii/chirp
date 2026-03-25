"""Chirp CLI — project scaffolding, dev server, and contract validation.

Entry point registered as ``chirp`` in ``pyproject.toml``::

    [project.scripts]
    chirp = "chirp.cli:main"
"""

import argparse
import sys


def _add_server_run_args(p: argparse.ArgumentParser) -> None:
    """Shared ``chirp run`` / ``chirp dev`` arguments."""
    p.add_argument(
        "app",
        help="Import string (e.g. myapp:app)",
    )
    p.add_argument("--host", default=None, help="Bind host address")
    p.add_argument("--port", type=int, default=None, help="Bind port number")
    p.add_argument(
        "--production",
        action="store_true",
        help="Run in production mode (multi-worker, all features enabled)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker count (0=auto-detect, production only)",
    )
    p.add_argument(
        "--metrics",
        action="store_true",
        help="Enable Prometheus /metrics endpoint",
    )
    p.add_argument(
        "--rate-limit",
        action="store_true",
        help="Enable per-IP rate limiting",
    )
    p.add_argument(
        "--queue",
        action="store_true",
        help="Enable request queueing",
    )
    p.add_argument(
        "--sentry-dsn",
        type=str,
        default=None,
        help="Sentry DSN for error tracking",
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the ``chirp`` command."""
    parser = argparse.ArgumentParser(
        prog="chirp",
        description="Chirp — A Python web framework for the modern web platform.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- chirp new --------------------------------------------------------
    new_parser = subparsers.add_parser("new", help="Create a new project")
    new_parser.add_argument("name", help="Project directory name")
    new_parser.add_argument(
        "--minimal",
        action="store_true",
        help="Generate a minimal single-file project",
    )
    new_parser.add_argument(
        "--sse",
        action="store_true",
        help="Include SSE boilerplate (EventStream, sse_scope)",
    )
    new_parser.add_argument(
        "--shell",
        action="store_true",
        help="Generate project with persistent app shell (topbar, sidebar)",
    )
    new_parser.add_argument(
        "--with-chirpui",
        action="store_true",
        help="Require ChirpUI templates (fail if chirp-ui is not installed)",
    )

    # -- chirp run --------------------------------------------------------
    run_parser = subparsers.add_parser("run", help="Start dev or production server")
    _add_server_run_args(run_parser)

    # -- chirp dev --------------------------------------------------------
    dev_parser = subparsers.add_parser(
        "dev",
        help="Development server with browser reload on template/CSS changes",
    )
    _add_server_run_args(dev_parser)

    # -- chirp check ------------------------------------------------------
    check_parser = subparsers.add_parser("check", help="Validate hypermedia contracts")
    check_parser.add_argument(
        "app",
        help="Import string (e.g. myapp:app)",
    )
    check_parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Exit with code 1 if contract warnings are present",
    )

    # -- chirp routes -----------------------------------------------------
    routes_parser = subparsers.add_parser("routes", help="List registered routes")
    routes_parser.add_argument(
        "app",
        help="Import string (e.g. myapp:app)",
    )

    # -- chirp security-check ---------------------------------------------
    sec_parser = subparsers.add_parser(
        "security-check",
        help="Audit app config against OWASP security checklist",
    )
    sec_parser.add_argument(
        "app",
        help="Import string (e.g. myapp:app)",
    )

    # -- chirp makemigrations ---------------------------------------------
    mig_parser = subparsers.add_parser(
        "makemigrations",
        help="Auto-generate schema migration from SQL diff",
    )
    mig_parser.add_argument(
        "--db",
        required=True,
        help="Database URL (e.g. sqlite:///app.db)",
    )
    mig_parser.add_argument(
        "--schema",
        required=True,
        help="Schema file path (SQL or Python with SCHEMA variable)",
    )
    mig_parser.add_argument(
        "--migrations-dir",
        default="migrations",
        help="Output directory for migration files (default: migrations)",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "new":
        from chirp.cli._new import create_project

        create_project(args)
    elif args.command == "run":
        from chirp.cli._run import run_server

        run_server(args)
    elif args.command == "dev":
        from chirp.cli._run import run_server

        args.dev_browser_reload = True
        run_server(args)
    elif args.command == "check":
        from chirp.cli._check import run_check

        run_check(args)
    elif args.command == "routes":
        from chirp.cli._routes import run_routes

        run_routes(args)
    elif args.command == "security-check":
        from chirp.cli._security_check import run_security_check

        run_security_check(args)
    elif args.command == "makemigrations":
        from chirp.cli._makemigrations import run_makemigrations

        run_makemigrations(args)
