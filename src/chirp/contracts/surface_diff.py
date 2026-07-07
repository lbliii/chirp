"""Hypermedia surface diff — git baseline comparison and MCP agent tool."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from chirp.contracts import check_hypermedia_surface
from chirp.contracts.diff import ContractDiff, diff_contract_dicts
from chirp.contracts.serialize import result_to_dict

if TYPE_CHECKING:
    from chirp.app import App


def collect_check_json(
    app: App,
    *,
    deploy: bool = False,
    include_info: bool = False,
    include_coverage: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Run contract validation and return ``(result, json_payload)``."""
    started = time.perf_counter()
    result = check_hypermedia_surface(app, deploy=deploy)
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result, result_to_dict(
        result,
        include_info=include_info,
        include_coverage=include_coverage,
    )


def collect_check_payload(
    app: App,
    *,
    deploy: bool = False,
    include_info: bool = False,
    include_coverage: bool = False,
) -> dict[str, Any]:
    """Run contract validation on *app* and return a stable JSON payload."""
    _, payload = collect_check_json(
        app,
        deploy=deploy,
        include_info=include_info,
        include_coverage=include_coverage,
    )
    return payload


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
        msg = "surface diff requires a git repository"
        raise RuntimeError(msg) from exc
    return Path(proc.stdout.strip())


def check_at_git_ref(
    app_import: str,
    base_ref: str,
    *,
    repo_root: Path,
    deploy: bool = False,
    include_info: bool = False,
    include_coverage: bool = False,
) -> dict[str, Any]:
    """Run ``chirp check --json`` against *app_import* at *base_ref* via a temp worktree."""
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
            raise RuntimeError(msg)

        try:
            cmd = [
                sys.executable,
                "-m",
                "chirp.cli",
                "check",
                app_import,
                "--json",
            ]
            if deploy:
                cmd.append("--deploy")
            if include_info:
                cmd.append("--include-info")
            if include_coverage:
                cmd.append("--coverage")

            env = os.environ.copy()
            env.setdefault("CHIRP_SKIP_CONTRACT_CHECKS", "1")
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
                raise RuntimeError(msg)
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                msg = f"Baseline check at {base_ref!r} returned invalid JSON"
                raise RuntimeError(msg) from exc
        finally:
            subprocess.run(  # noqa: S603
                ["git", "worktree", "remove", "--force", str(worktree)],  # noqa: S607
                cwd=repo_root,
                capture_output=True,
            )


def collect_surface_diff(
    app: App,
    app_import: str,
    base_ref: str,
    *,
    repo_root: Path | None = None,
    deploy: bool = False,
    include_info: bool = False,
) -> tuple[ContractDiff, dict[str, Any]]:
    """Diff hypermedia contracts for *app* against *base_ref*."""
    root = repo_root or find_git_root()
    current = collect_check_payload(
        app,
        deploy=deploy,
        include_info=include_info,
        include_coverage=True,
    )
    baseline = check_at_git_ref(
        app_import,
        base_ref,
        repo_root=root,
        deploy=deploy,
        include_info=include_info,
        include_coverage=True,
    )
    diff = diff_contract_dicts(baseline, current)
    payload = {
        "base_ref": base_ref,
        "app_import": app_import,
        "baseline": baseline,
        "current": current,
        "diff": {
            "added": list(diff.added),
            "removed": list(diff.removed),
            "coverage": list(diff.coverage_changes),
        },
        "summary_lines": diff.summary_lines(),
    }
    return diff, payload


def register_surface_diff_tool(
    app: App,
    app_import: str,
    *,
    default_base_ref: str = "origin/main",
) -> None:
    """Register ``chirp_surface_diff`` on *app* for MCP agent consumption (issue #344)."""

    @app.tool(
        "chirp_surface_diff",
        description=(
            "Diff this app's hypermedia contract surface against a git base ref. "
            "Reports added/removed issues for routes, SSE bindings, forms, and OOB targets."
        ),
    )
    def chirp_surface_diff(
        base_ref: str = default_base_ref,
        deploy: bool = False,
        include_info: bool = False,
    ) -> dict[str, Any]:
        _, payload = collect_surface_diff(
            app,
            app_import,
            base_ref,
            deploy=deploy,
            include_info=include_info,
        )
        return payload
