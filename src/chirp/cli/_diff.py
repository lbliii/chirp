"""``chirp diff`` — hypermedia contract diff against a git base ref."""

from __future__ import annotations

import argparse
import json
import os
import sys
from threading import RLock

from chirp.cli._inspection import (
    InspectionResult,
    emit_terminal_result,
    inspection_error,
    resolution_error,
)
from chirp.cli._resolve import resolve_app
from chirp.contracts.surface_diff import collect_surface_diff, find_git_root

_DIFF_RESOLUTION_LOCK = RLock()


def run_diff(args: argparse.Namespace) -> None:
    """Diff hypermedia contracts for *args.app* against *args.base*."""
    emit_terminal_result(
        collect_diff_result(
            args.app,
            args.base,
            json_output=args.json,
            warnings_as_errors=args.warnings_as_errors,
            deploy=args.deploy,
            include_info=args.include_info,
        )
    )


def collect_diff_result(
    app_import: str,
    base: str,
    *,
    json_output: bool = False,
    warnings_as_errors: bool = False,
    deploy: bool = False,
    include_info: bool = False,
) -> InspectionResult:
    """Return a stable git-baseline diff plus CLI presentation metadata."""
    try:
        repo_root = find_git_root()
    except RuntimeError as exc:
        return inspection_error(
            code="CHIRP_GIT_ROOT",
            message=str(exc),
            suggestion="Run this command from inside the application's git repository.",
            context={"base_ref": base, "app_import": app_import},
        )

    # App resolution consults process-global import and environment state. The
    # lock serializes the idempotent publication under free-threaded MCP calls.
    with _DIFF_RESOLUTION_LOCK:
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        os.environ.setdefault("CHIRP_SKIP_CONTRACT_CHECKS", "1")
        try:
            app = resolve_app(app_import)
        except (ModuleNotFoundError, AttributeError, TypeError) as exc:
            return resolution_error(app_import, exc)

    try:
        diff, payload = collect_surface_diff(
            app,
            app_import,
            base,
            repo_root=repo_root,
            deploy=deploy,
            include_info=include_info,
        )
    except RuntimeError as exc:
        return inspection_error(
            code="CHIRP_DIFF_FAILED",
            message=str(exc),
            suggestion="Verify the base ref and that the app imports at both revisions.",
            context={"base_ref": base, "app_import": app_import},
        )

    if json_output:
        terminal_text = json.dumps(payload, indent=2)
    else:
        lines = [f"Hypermedia surface change (vs {base}):"]
        lines.extend(diff.summary_lines()[1:] if diff.has_changes else ["  (no issue changes)"])
        terminal_text = "\n".join(lines)

    strict = warnings_as_errors or deploy
    failed = bool(diff.added_errors or (strict and diff.added_warnings))
    return InspectionResult(payload, terminal_text=terminal_text, exit_code=1 if failed else 0)
