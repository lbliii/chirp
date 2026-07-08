"""``chirp check`` — hypermedia contract validation command.

Resolves an import string to a chirp App and runs contract validation,
printing results to stdout.  Exits with code 1 if errors are found.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from chirp.cli._inspection import (
    InspectionResult,
    emit_terminal_result,
    inspection_error,
    resolution_error,
)
from chirp.cli._resolve import resolve_app
from chirp.contracts.diff import diff_contract_dicts
from chirp.contracts.surface_diff import collect_check_json
from chirp.server.terminal_checks import format_check_result


def run_check(args: argparse.Namespace) -> None:
    """Validate hypermedia contracts for a chirp app.

    Resolves ``args.app`` to a Chirp App, collects the structured contract
    result, then applies the established terminal presentation and exit policy.
    """
    emit_terminal_result(
        collect_check_result(
            args.app,
            warnings_as_errors=args.warnings_as_errors,
            coverage=args.coverage,
            deploy=args.deploy,
            json_output=args.json,
            baseline=args.baseline,
            include_info=args.include_info,
        )
    )


def collect_check_result(
    app_import: str,
    *,
    warnings_as_errors: bool = False,
    coverage: bool = False,
    deploy: bool = False,
    json_output: bool = False,
    baseline: str | None = None,
    include_info: bool = False,
) -> InspectionResult:
    """Return a stable contract payload plus CLI-only presentation metadata."""
    try:
        app = resolve_app(app_import)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        return resolution_error(app_import, exc)

    result, payload = collect_check_json(
        app,
        deploy=deploy,
        include_info=include_info,
        include_coverage=coverage,
    )
    strict = warnings_as_errors or deploy

    if baseline:
        return _baseline_result(
            payload,
            baseline=baseline,
            json_output=json_output,
            warnings_as_errors=strict,
        )

    terminal_text = (
        json.dumps(payload, indent=2)
        if json_output
        else format_check_result(
            result,
            color=None,
            fragment_target_registry=app._contract_checks._registry(app),
            verbose_registry=app.config.debug,
            show_coverage=coverage,
        )
    )
    exit_code = 1 if not result.ok or (strict and result.warnings) else 0
    return InspectionResult(payload, terminal_text=terminal_text, exit_code=exit_code)


def _baseline_result(
    current: dict[str, Any],
    *,
    baseline: str,
    json_output: bool,
    warnings_as_errors: bool,
) -> InspectionResult:
    """Compare a current structured check with a stored baseline."""
    baseline_path = Path(baseline)
    try:
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return inspection_error(
            code="CHIRP_BASELINE_INVALID",
            message=f"Could not read contract baseline {baseline!r}: {exc}",
            suggestion="Generate the baseline with `chirp check APP --json` and retry.",
            context={"baseline": baseline},
        )
    if not isinstance(baseline_payload, dict):
        return inspection_error(
            code="CHIRP_BASELINE_INVALID",
            message=f"Could not read contract baseline {baseline!r}: root must be a JSON object",
            suggestion="Generate the baseline with `chirp check APP --json` and retry.",
            context={"baseline": baseline},
        )

    diff = diff_contract_dicts(baseline_payload, current)
    payload = {
        "current": current,
        "diff": {
            "added": list(diff.added),
            "removed": list(diff.removed),
            "coverage": list(diff.coverage_changes),
        },
    }
    terminal_text = (
        json.dumps(payload, indent=2) if json_output else "\n".join(diff.summary_lines())
    )
    failed = bool(diff.added_errors or (warnings_as_errors and diff.added_warnings))
    return InspectionResult(payload, terminal_text=terminal_text, exit_code=1 if failed else 0)
