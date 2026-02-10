"""``chirp check`` — hypermedia contract validation command.

Resolves an import string to a chirp App and runs contract validation,
printing results to stdout.  Exits with code 1 if errors are found.
"""

import argparse
import sys

from chirp.cli._resolve import resolve_app


def run_check(args: argparse.Namespace) -> None:
    """Validate hypermedia contracts for a chirp app.

    Resolves ``args.app`` to a chirp App instance and delegates to
    ``App.check()``, which prints validation results and raises
    ``SystemExit(1)`` on failure.
    """
    try:
        app = resolve_app(args.app)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    app.check()
