"""``chirp diff`` — hypermedia contract diff against a git base ref."""

from __future__ import annotations

import argparse
import json
import os
import sys

from chirp.cli._resolve import resolve_app
from chirp.contracts.surface_diff import collect_surface_diff, find_git_root


def run_diff(args: argparse.Namespace) -> None:
    """Diff hypermedia contracts for *args.app* against *args.base*."""
    repo_root = find_git_root()
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    os.environ.setdefault("CHIRP_SKIP_CONTRACT_CHECKS", "1")

    try:
        app = resolve_app(args.app)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    diff, payload = collect_surface_diff(
        app,
        args.app,
        args.base,
        repo_root=repo_root,
        deploy=args.deploy,
        include_info=args.include_info,
    )

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Hypermedia surface change (vs {args.base}):")
        if diff.has_changes:
            for line in diff.summary_lines()[1:]:
                print(line)
        else:
            print("  (no issue changes)")

    warnings_as_errors = args.warnings_as_errors or args.deploy
    if diff.added_errors:
        raise SystemExit(1)
    if warnings_as_errors and diff.added_warnings:
        raise SystemExit(1)
