"""Fresh-environment install + import smoke for supported dependency profiles.

Issue #910 / decision #908. Isolation belongs here (and in the
``install-smoke`` workflow), not in ordinary contributor ``uv sync --group
dev`` or specialized capability lanes (#906 / #917).

Usage::

    python scripts/install_smoke.py --list
    python scripts/install_smoke.py --matrix-json
    python scripts/install_smoke.py --profile minimal --python 3.14t
    python scripts/install_smoke.py --all

Failures always name the profile ID and the resolution path.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Sequence
from pathlib import Path

# Allow ``python scripts/install_smoke.py`` without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dependency_profiles import (
    PROFILE_BY_ID,
    SUPPORTED_PROFILES,
    DependencyProfile,
    ci_matrix_entries,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


class InstallSmokeError(RuntimeError):
    """Install or import smoke failed for a named profile."""

    def __init__(self, profile: DependencyProfile, stage: str, detail: str) -> None:
        self.profile = profile
        self.stage = stage
        message = (
            f"install-smoke FAILED\n"
            f"  profile:    {profile.id}\n"
            f"  stage:      {stage}\n"
            f"  resolution: {profile.resolution}\n"
            f"  detail:\n{textwrap.indent(detail.rstrip(), '    ')}"
        )
        super().__init__(message)


def _run(
    cmd: Sequence[str],
    *,
    env: dict[str, str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _format_cmd_failure(proc: subprocess.CompletedProcess[str]) -> str:
    parts = [
        f"command: {' '.join(proc.args) if isinstance(proc.args, list) else proc.args}",
        f"exit: {proc.returncode}",
    ]
    if proc.stdout.strip():
        parts.append(f"stdout:\n{proc.stdout.rstrip()}")
    if proc.stderr.strip():
        parts.append(f"stderr:\n{proc.stderr.rstrip()}")
    return "\n".join(parts)


def _smoke_source(profile: DependencyProfile) -> str:
    lines = [f"import {name}" for name in profile.import_modules]
    lines.extend(profile.smoke_statements)
    lines.append("print('ok')")
    return "\n".join(lines)


def smoke_profile(
    profile: DependencyProfile,
    *,
    python: str,
    repo_root: Path = _REPO_ROOT,
    work_root: Path | None = None,
    keep: bool = False,
) -> Path:
    """Install *profile* into a fresh env and run its import smoke.

    Returns the temporary work directory used (caller may inspect it).
    """
    cleanup = work_root is None and not keep
    work = (
        Path(work_root)
        if work_root is not None
        else Path(tempfile.mkdtemp(prefix="chirp-install-smoke-"))
    )
    venv = work / "venv"
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(venv)
    # Free-threaded posture when the requested interpreter is a ``t`` build.
    if python.endswith("t"):
        env["PYTHON_GIL"] = "0"
    else:
        env.pop("PYTHON_GIL", None)

    try:
        create = _run(
            ["uv", "venv", "--python", python, str(venv)],
            env=env,
            cwd=repo_root,
        )
        if create.returncode != 0:
            raise InstallSmokeError(profile, "venv", _format_cmd_failure(create))

        sync_cmd = [
            "uv",
            "sync",
            "--no-sources",
            "--python",
            python,
            *profile.sync_args,
        ]
        sync = _run(sync_cmd, env=env, cwd=repo_root)
        if sync.returncode != 0:
            raise InstallSmokeError(profile, "sync", _format_cmd_failure(sync))

        if profile.post_pip_args:
            pin = _run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(venv / "bin" / "python"),
                    *profile.post_pip_args,
                ],
                env=env,
                cwd=repo_root,
            )
            if pin.returncode != 0:
                raise InstallSmokeError(profile, "post-pip", _format_cmd_failure(pin))

        python_bin = venv / "bin" / "python"
        smoke = _run(
            [str(python_bin), "-c", _smoke_source(profile)],
            env=env,
            cwd=repo_root,
        )
        if smoke.returncode != 0:
            raise InstallSmokeError(profile, "import", _format_cmd_failure(smoke))
        return work
    finally:
        if cleanup and work.exists():
            shutil.rmtree(work, ignore_errors=True)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        metavar="ID",
        help="Profile ID to smoke (repeatable). Default: all supported profiles.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Smoke every supported profile (default when --profile omitted).",
    )
    parser.add_argument(
        "--python",
        default="3.14t",
        help="Python version selector for uv (default: 3.14t).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print supported profile IDs and exit.",
    )
    parser.add_argument(
        "--matrix-json",
        action="store_true",
        help="Print the CI matrix (profile x python) as JSON and exit.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep temporary environments under --work-root (or a temp dir).",
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        help="Parent directory for per-profile workdirs (default: system temp).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.list:
        for profile in SUPPORTED_PROFILES:
            print(f"{profile.id}\t{profile.resolution}")
        return 0

    if args.matrix_json:
        json.dump(ci_matrix_entries(), sys.stdout)
        sys.stdout.write("\n")
        return 0

    if args.profiles:
        unknown = [p for p in args.profiles if p not in PROFILE_BY_ID]
        if unknown:
            print(
                f"error: unknown profile(s): {', '.join(unknown)}\n"
                f"known: {', '.join(PROFILE_BY_ID)}",
                file=sys.stderr,
            )
            return 2
        selected = tuple(PROFILE_BY_ID[p] for p in args.profiles)
    else:
        selected = SUPPORTED_PROFILES

    failures = 0
    for profile in selected:
        label = f"{profile.id} @ {args.python}"
        print(f"==> {label}")
        print(f"    resolution: {profile.resolution}")
        work: Path | None = None
        if args.work_root is not None:
            work = args.work_root / f"{profile.id}-{args.python.replace('.', '_')}"
            work.mkdir(parents=True, exist_ok=True)
        try:
            smoke_profile(
                profile,
                python=args.python,
                work_root=work,
                keep=args.keep or work is not None,
            )
        except InstallSmokeError as exc:
            failures += 1
            print(str(exc), file=sys.stderr)
            continue
        print(f"    PASS {label}")

    if failures:
        print(
            f"\n{failures} profile(s) failed install-smoke (see profile + resolution above).",
            file=sys.stderr,
        )
        return 1
    print(f"\nAll {len(selected)} profile(s) passed install-smoke.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
