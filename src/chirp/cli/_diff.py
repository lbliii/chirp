"""``chirp diff`` — hypermedia contract diff against a git base ref."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from chirp.cli._resolve import resolve_app
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.diff import diff_contract_dicts
from chirp.contracts.serialize import result_to_dict


def collect_check_json(
    app,
    *,
    deploy: bool = False,
    include_info: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Run contract validation and return ``(result, json_payload)``."""
    started = time.perf_counter()
    result = check_hypermedia_surface(app, deploy=deploy)
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result, result_to_dict(result, include_info=include_info)


def find_git_root(start: Path | None = None) -> Path:
    """Return the git repository root for *start* (default: cwd)."""
    cwd = Path.cwd() if start is None else start if start.is_dir() else start.parent
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        msg = "chirp diff requires a git repository"
        raise SystemExit(msg) from exc
    return Path(proc.stdout.strip())


def check_at_git_ref(
    app: str,
    base_ref: str,
    *,
    repo_root: Path,
    deploy: bool = False,
    include_info: bool = False,
) -> dict[str, Any]:
    """Run ``chirp check --json`` against *app* at *base_ref* via a temp worktree."""
    with tempfile.TemporaryDirectory(prefix="chirp-diff-") as tmp:
        worktree = Path(tmp) / "base"
        add = subprocess.run(  # noqa: S603
            ["git", "worktree", "add", "--detach", str(worktree), base_ref],  # noqa: S607
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if add.returncode != 0:
            detail = (add.stderr or add.stdout or "").strip()
            msg = f"Could not create worktree at {base_ref!r}"
            if detail:
                msg = f"{msg}: {detail}"
            raise SystemExit(msg)

        try:
            cmd = [
                sys.executable,
                "-m",
                "chirp.cli",
                "check",
                app,
                "--json",
            ]
            if deploy:
                cmd.append("--deploy")
            if include_info:
                cmd.append("--include-info")

            env = os.environ.copy()
            env.setdefault("CHIRP_SKIP_CONTRACT_CHECKS", "1")
            # Load app modules from the base ref; keep the installed chirp framework.
            env["PYTHONPATH"] = str(worktree) + os.pathsep + env.get("PYTHONPATH", "")

            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=worktree,
                env=env,
                capture_output=True,
                text=True,
            )
            if not proc.stdout.strip():
                detail = (proc.stderr or "").strip()
                msg = f"Baseline check at {base_ref!r} produced no JSON output"
                if detail:
                    msg = f"{msg}: {detail}"
                raise SystemExit(msg)
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                msg = f"Baseline check at {base_ref!r} returned invalid JSON"
                raise SystemExit(msg) from exc
        finally:
            subprocess.run(  # noqa: S603
                ["git", "worktree", "remove", "--force", str(worktree)],  # noqa: S607
                cwd=repo_root,
                capture_output=True,
            )


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

    _, current = collect_check_json(
        app,
        deploy=args.deploy,
        include_info=args.include_info,
    )

    baseline = check_at_git_ref(
        args.app,
        args.base,
        repo_root=repo_root,
        deploy=args.deploy,
        include_info=args.include_info,
    )
    diff = diff_contract_dicts(baseline, current)

    if args.json:
        print(
            json.dumps(
                {
                    "base_ref": args.base,
                    "baseline": baseline,
                    "current": current,
                    "diff": {
                        "added": list(diff.added),
                        "removed": list(diff.removed),
                    },
                },
                indent=2,
            )
        )
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
