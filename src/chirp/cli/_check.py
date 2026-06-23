"""``chirp check`` — hypermedia contract validation command.

Resolves an import string to a chirp App and runs contract validation,
printing results to stdout.  Exits with code 1 if errors are found.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chirp.cli._resolve import resolve_app
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.diff import diff_contract_dicts
from chirp.contracts.serialize import result_to_dict


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

    if args.json or args.baseline:
        _run_structured_check(app, args)
        return

    app.check(
        deploy=args.deploy,
        warnings_as_errors=args.warnings_as_errors or args.deploy,
        coverage=args.coverage,
    )


def _run_structured_check(app, args: argparse.Namespace) -> None:
    import time

    started = time.perf_counter()
    result = check_hypermedia_surface(app, deploy=args.deploy)
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    payload = result_to_dict(result, include_info=args.include_info)

    if args.baseline:
        baseline_path = Path(args.baseline)
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        diff = diff_contract_dicts(baseline, payload)
        if not args.json:
            for line in diff.summary_lines():
                print(line)
        else:
            print(
                json.dumps(
                    {
                        "current": payload,
                        "diff": {
                            "added": list(diff.added),
                            "removed": list(diff.removed),
                        },
                    },
                    indent=2,
                )
            )
        warnings_as_errors = args.warnings_as_errors or args.deploy
        if diff.added_errors:
            raise SystemExit(1)
        if warnings_as_errors and diff.added_warnings:
            raise SystemExit(1)
        if not result.ok and not args.baseline:
            raise SystemExit(1)
        return

    print(json.dumps(payload, indent=2))
    warnings_as_errors = args.warnings_as_errors or args.deploy
    if not result.ok or (warnings_as_errors and result.warnings):
        raise SystemExit(1)
