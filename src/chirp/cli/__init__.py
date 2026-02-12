"""Chirp CLI — project scaffolding, dev server, and contract validation.

Entry point registered as ``chirp`` in ``pyproject.toml``::

    [project.scripts]
    chirp = "chirp.cli:main"
"""

import argparse
import sys


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

    # -- chirp run --------------------------------------------------------
    run_parser = subparsers.add_parser("run", help="Start dev or production server")
    run_parser.add_argument(
        "app",
        help="Import string (e.g. myapp:app)",
    )
    run_parser.add_argument("--host", default=None, help="Bind host address")
    run_parser.add_argument("--port", type=int, default=None, help="Bind port number")

    # Production mode flags
    run_parser.add_argument(
        "--production",
        action="store_true",
        help="Run in production mode (multi-worker, all features enabled)",
    )
    run_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker count (0=auto-detect, production only)",
    )
    run_parser.add_argument(
        "--metrics",
        action="store_true",
        help="Enable Prometheus /metrics endpoint",
    )
    run_parser.add_argument(
        "--rate-limit",
        action="store_true",
        help="Enable per-IP rate limiting",
    )
    run_parser.add_argument(
        "--queue",
        action="store_true",
        help="Enable request queueing",
    )
    run_parser.add_argument(
        "--sentry-dsn",
        type=str,
        default=None,
        help="Sentry DSN for error tracking",
    )

    # -- chirp check ------------------------------------------------------
    check_parser = subparsers.add_parser("check", help="Validate hypermedia contracts")
    check_parser.add_argument(
        "app",
        help="Import string (e.g. myapp:app)",
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
    elif args.command == "check":
        from chirp.cli._check import run_check

        run_check(args)
