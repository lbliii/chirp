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
    run_parser = subparsers.add_parser("run", help="Start dev server")
    run_parser.add_argument(
        "app",
        help="Import string (e.g. myapp:app)",
    )
    run_parser.add_argument("--host", default=None, help="Bind host address")
    run_parser.add_argument("--port", type=int, default=None, help="Bind port number")

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
