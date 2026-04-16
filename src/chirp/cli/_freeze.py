"""``chirp freeze`` — render routes to static HTML.

Resolves an import string to a chirp App, walks the route table,
renders each freezable URL, and writes static HTML to disk.
"""

import argparse
import sys
from pathlib import Path

import anyio

from chirp.cli._resolve import resolve_app
from chirp.freeze import freeze


async def _run(app_string: str, output: Path, exclude: list[str] | None) -> None:
    from chirp.app import App

    try:
        app: App = resolve_app(app_string)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    result = await freeze(app, output, exclude=exclude)

    # Summary
    print(f"\nFroze {result.pages_written} pages to {output}/")
    if result.pages_skipped:
        print(f"  Skipped: {result.pages_skipped}")
    if result.errors:
        print(f"  Errors:  {len(result.errors)}")
        for err in result.errors:
            print(f"    {err}", file=sys.stderr)
    print(f"  Time:    {result.elapsed:.3f}s")

    if result.errors:
        raise SystemExit(1)


def run_freeze(args: argparse.Namespace) -> None:
    """Freeze a chirp app to static HTML files."""
    output = Path(args.output)
    exclude = args.exclude if hasattr(args, "exclude") and args.exclude else None
    anyio.run(lambda: _run(args.app, output, exclude))
