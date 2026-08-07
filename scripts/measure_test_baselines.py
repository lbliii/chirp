#!/usr/bin/env python3
"""Measure representative local test-duration baselines for issue #923.

Measurement only — does not rebalance xdist, change markers, or drop coverage.

Examples::

    # Collect node counts for named groups (seconds).
    uv run python scripts/measure_test_baselines.py --profile collect

    # Time cheap local paths with run-to-run variance (default).
    uv run python scripts/measure_test_baselines.py --profile fast --repeats 3

    # Mirror the main CI ``test`` job command (minutes; uses -n 4 + coverage).
    uv run python scripts/measure_test_baselines.py --profile ci-mirror

    # Sequential full suite (expensive; optional confirmation sample).
    uv run python scripts/measure_test_baselines.py --profile sequential

CI wall times are sourced separately via ``gh run view`` / Actions job logs;
see ``docs/test-duration-baseline-923.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Named families matching epic #900 / issue #923 scope language.
COLLECT_GROUPS: dict[str, list[str]] = {
    "all_default_paths": [],  # testpaths from pytest.ini (tests + examples)
    "tests_only": ["tests"],
    "examples_only": ["examples"],
    "invariants": [
        "tests/test_lazy_imports.py",
        "tests/test_public_api_docs.py",
    ],
    "contracts": ["tests/contracts"],
    "interop_query": ["tests/interop/test_query_wire.py"],
    "postgres_live_paths": [
        "tests/test_schema_introspect.py",
        "tests/test_pelt/test_connection_integration.py",
        "tests/test_pelt/test_tls_auth_integration.py",
        "tests/test_jobs_postgres.py",
    ],
    "browser_smoke_paths": [
        "examples/chirpui/lucky_cat/test_browser_smoke.py",
        "examples/standalone/htmx_managed/test_browser_smoke.py",
        "examples/standalone/devtools_htmx4/test_browser_smoke.py",
        "examples/standalone/webmcp_form/test_browser_smoke.py",
        "tests/contracts/test_query_devtools_browser.py",
        "tests/contracts/test_query_cors_browser.py",
        "tests/contracts/test_accessibility_interactions_browser.py",
    ],
}

# Exact CI ``test`` job argv after ``uv run`` (see .github/workflows/ci.yml).
CI_MIRROR_ARGS = [
    "pytest",
    "-q",
    "--tb=short",
    "--timeout=60",
    "-m",
    "not slow",
    "--ignore=examples/chirpui/lucky_cat/test_browser_smoke.py",
    "-n",
    "4",
    "--dist",
    "loadgroup",
    "--cov",
    "--cov-report=term",
]

COLLECT_NOT_SLOW = [
    "pytest",
    "--collect-only",
    "-q",
    "-m",
    "not slow",
    "--ignore=examples/chirpui/lucky_cat/test_browser_smoke.py",
]


@dataclass(frozen=True, slots=True)
class EnvSnapshot:
    """Host + interpreter identity for a measurement receipt."""

    recorded_at: str
    git_revision: str
    cwd: str
    platform: str
    machine: str
    processor: str
    python_version: str
    python_implementation: str
    executable: str
    gil_enabled: bool | None
    cpu_count: int | None
    env_flags: dict[str, str]


@dataclass(slots=True)
class CommandResult:
    """One timed subprocess invocation."""

    name: str
    argv: list[str]
    wall_s: float
    returncode: int
    stdout_tail: str
    stderr_tail: str
    parsed: dict[str, object] = field(default_factory=dict)


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except OSError, subprocess.CalledProcessError:
        return "unknown"


def _gil_enabled() -> bool | None:
    if hasattr(sys, "_is_gil_enabled"):
        return bool(sys._is_gil_enabled())  # type: ignore[attr-defined]
    return None


def snapshot_env() -> EnvSnapshot:
    """Capture the measurement environment."""
    flags = {
        key: os.environ[key]
        for key in ("PYTHON_GIL", "CHIRP_TEST_PG_DSN", "CI")
        if key in os.environ
    }
    return EnvSnapshot(
        recorded_at=datetime.now(UTC).isoformat(),
        git_revision=_git_revision(),
        cwd=str(ROOT),
        platform=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor() or platform.machine(),
        python_version=sys.version.replace("\n", " "),
        python_implementation=platform.python_implementation(),
        executable=sys.executable,
        gil_enabled=_gil_enabled(),
        cpu_count=os.cpu_count(),
        env_flags=flags,
    )


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


_SUMMARY_RE = re.compile(
    r"(?P<body>(?:\d+ (?:passed|failed|skipped|deselected|xfailed|xpassed|"
    r"warning|warnings|error|errors)(?:, )?)+) in (?P<pytest_s>[0-9.]+)s"
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_COUNT_TOKEN_RE = re.compile(
    r"(?P<n>\d+) (?P<kind>passed|failed|skipped|deselected|xfailed|xpassed|"
    r"warnings|warning|errors|error)"
)
_COLLECTED_RE = re.compile(r"(?P<n>\d+) tests? collected(?: in (?P<s>[0-9.]+)s)?")
_COLLECTED_DESELECT_RE = re.compile(
    r"(?P<n>\d+)/(?P<total>\d+) tests collected \((?P<deselected>\d+) deselected\)"
)
# pytest --collect-only -q prints one ``path: N`` line per module (pytest 9).
_PER_FILE_COUNT_RE = re.compile(
    r"^(?:examples|tests)/[\w./-]+\.py: (?P<n>\d+)\s*$",
    re.MULTILINE,
)
_SKIPPED_RE = re.compile(r"^SKIPPED \[(\d+)\]", re.MULTILINE)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def parse_pytest_output(text: str) -> dict[str, object]:
    """Extract node counts and pytest's own duration when present."""
    text = _strip_ansi(text)
    out: dict[str, object] = {}
    m = _SUMMARY_RE.search(text)
    if m:
        out["pytest_reported_s"] = float(m.group("pytest_s"))
        for token in _COUNT_TOKEN_RE.finditer(m.group("body")):
            kind = token.group("kind")
            if kind in {"warning", "warnings"}:
                key = "warnings"
            elif kind in {"error", "errors"}:
                key = "errors"
            else:
                key = kind
            out[key] = int(token.group("n"))
    deselected = _COLLECTED_DESELECT_RE.search(text)
    if deselected:
        out["collected"] = int(deselected.group("n"))
        out["collected_total_before_deselect"] = int(deselected.group("total"))
        out["deselected"] = int(deselected.group("deselected"))
        if deselected.groupdict().get("s"):
            pass
    cm = _COLLECTED_RE.search(text)
    if cm and "collected" not in out:
        out["collected"] = int(cm.group("n"))
        if cm.group("s"):
            out["collect_reported_s"] = float(cm.group("s"))
    elif cm and cm.group("s"):
        out["collect_reported_s"] = float(cm.group("s"))
    per_file = [int(match.group("n")) for match in _PER_FILE_COUNT_RE.finditer(text)]
    if per_file:
        out["per_file_modules"] = len(per_file)
        out["collected_from_per_file"] = sum(per_file)
        if "collected" not in out:
            out["collected"] = sum(per_file)
    skipped_hits = _SKIPPED_RE.findall(text)
    if skipped_hits and "skipped" not in out:
        out["skipped_reported"] = sum(int(n) for n in skipped_hits)
    return out


def run_command(name: str, argv: list[str], *, env: dict[str, str] | None = None) -> CommandResult:
    """Run ``argv`` under the project root and capture wall time."""
    merged = os.environ.copy()
    if env:
        merged.update(env)
    started = time.perf_counter()
    proc = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )
    wall = time.perf_counter() - started
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return CommandResult(
        name=name,
        argv=argv,
        wall_s=round(wall, 3),
        returncode=proc.returncode,
        stdout_tail=_tail(proc.stdout or ""),
        stderr_tail=_tail(proc.stderr or ""),
        parsed=parse_pytest_output(combined),
    )


def uv_run(args: list[str]) -> list[str]:
    """Prefix argv with ``uv run`` for the worktree venv."""
    return ["uv", "run", *args]


def measure_collect(groups: dict[str, list[str]]) -> list[CommandResult]:
    """Collect-only node counts per named group."""
    results: list[CommandResult] = []
    for name, paths in groups.items():
        argv = uv_run(["pytest", "--collect-only", "-q", *paths])
        results.append(run_command(f"collect:{name}", argv))
    # CI-shaped collect (not slow, ignore browser smoke path).
    results.append(run_command("collect:ci_mirror_shape", uv_run(COLLECT_NOT_SLOW)))
    return results


def measure_fast(repeats: int) -> list[CommandResult]:
    """Time preflight + invariants + contracts with optional repeats."""
    results = [
        run_command(f"preflight#{i}", uv_run(["poe", "preflight"])) for i in range(1, repeats + 1)
    ]
    results.extend(
        run_command(
            f"invariants#{i}",
            uv_run(
                [
                    "pytest",
                    "tests/test_lazy_imports.py",
                    "tests/test_public_api_docs.py",
                    "-q",
                    "--timeout=60",
                    "-ra",
                ]
            ),
        )
        for i in range(1, repeats + 1)
    )
    # Contracts once with durations (setup/call signal for #900 planning).
    # Keep running after failures so wall time remains a useful sample when a
    # single unrelated local flake appears (measurement, not gate).
    results.append(
        run_command(
            "contracts_durations",
            uv_run(
                [
                    "pytest",
                    "tests/contracts",
                    "-q",
                    "--timeout=60",
                    "--durations=25",
                    "--maxfail=5",
                ]
            ),
        )
    )
    return results


def measure_ci_mirror() -> CommandResult:
    """Run the main CI ``test`` job command locally."""
    env = {"PYTHON_GIL": os.environ.get("PYTHON_GIL", "0")}
    return run_command("ci_mirror_test_job", uv_run(CI_MIRROR_ARGS), env=env)


def measure_sequential() -> CommandResult:
    """Run the authoritative full-suite entrypoint sequentially."""
    return run_command(
        "sequential_full_suite",
        uv_run(["pytest", "tests", "-q", "--timeout=60"]),
    )


def summarize_repeats(results: list[CommandResult], prefix: str) -> dict[str, object]:
    """Compute min/median/max wall times for repeated command names."""
    walls = [r.wall_s for r in results if r.name.startswith(prefix)]
    if not walls:
        return {}
    return {
        "n": len(walls),
        "min_s": min(walls),
        "median_s": statistics.median(walls),
        "max_s": max(walls),
        "stdev_s": statistics.stdev(walls) if len(walls) > 1 else 0.0,
        "samples_s": walls,
    }


def build_receipt(
    profile: str,
    results: list[CommandResult],
    *,
    notes: list[str],
) -> dict[str, object]:
    """Assemble a JSON-serializable baseline receipt."""
    env = snapshot_env()
    return {
        "issue": 923,
        "parent": 900,
        "saga": 896,
        "profile": profile,
        "purpose": (
            "Representative local/CI test-duration baseline before execution "
            "strategy changes. Measurement only."
        ),
        "environment": asdict(env),
        "commands": [asdict(r) for r in results],
        "variance": {
            "preflight": summarize_repeats(results, "preflight#"),
            "invariants": summarize_repeats(results, "invariants#"),
        },
        "notes": notes,
        "ci_methodology": {
            "workflow": ".github/workflows/ci.yml",
            "source": "GitHub Actions job startedAt/completedAt via gh run view",
            "main_test_command": " ".join(CI_MIRROR_ARGS),
            "critical_path_job": "test",
            "service_dominated_jobs": [
                "test-postgres (matrix)",
                "data-pg-gil-gate",
                "browser-smoke (Playwright install + Chromium)",
                "query-interop (nginx + optional protocol clients)",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("collect", "fast", "ci-mirror", "sequential", "all-local"),
        default="fast",
        help="Which measurement recipe to run (default: fast).",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Repeats for variance-sensitive fast commands (default: 3).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON receipt to this path (default: stdout only).",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Omit bulky stdout/stderr tails from the JSON receipt (keep FAILED lines).",
    )
    args = parser.parse_args(argv)

    results: list[CommandResult] = []
    notes: list[str] = [
        "Do not treat service-dominated CI jobs as interchangeable with the "
        "main free-threaded pytest job when setting budgets (#919).",
        "Acceptance #923: n/a — measurement receipt; no behavioral test.",
    ]

    if args.profile in {"collect", "all-local"}:
        results.extend(measure_collect(COLLECT_GROUPS))
    if args.profile in {"fast", "all-local"}:
        results.extend(measure_fast(args.repeats))
    if args.profile in {"ci-mirror", "all-local"}:
        notes.append(
            "ci-mirror matches the main CI test job argv; local wall time "
            "will differ from ubuntu-latest runners."
        )
        results.append(measure_ci_mirror())
    if args.profile == "sequential":
        notes.append(
            "sequential profile uses `uv run pytest tests -q` (tests/ only), "
            "the steward full-suite entrypoint; examples/ are separate."
        )
        results.append(measure_sequential())

    optional_bad = [
        r for r in results if r.returncode != 0 and r.name.startswith("collect:browser_smoke")
    ]
    if optional_bad:
        notes.append(
            "browser_smoke_paths collection requires "
            "`uv sync --group dev --group browser`; failure without Playwright "
            "is recorded, not treated as a hard baseline error."
        )
        print(
            "optional/non-blocking failures (missing browser deps expected): "
            + ", ".join(r.name for r in optional_bad),
            file=sys.stderr,
        )

    receipt = build_receipt(args.profile, results, notes=notes)
    if args.compact:
        for cmd in receipt["commands"]:
            if not isinstance(cmd, dict):
                continue
            out = str(cmd.get("stdout_tail") or "")
            failed = [ln for ln in out.splitlines() if ln.startswith("FAILED ")]
            durations = [
                ln
                for ln in out.splitlines()
                if "s call" in ln or "s setup" in ln or "slowest" in ln.lower()
            ]
            cmd["stdout_tail"] = "\n".join(failed[:40])
            err = str(cmd.get("stderr_tail") or "")
            cmd["stderr_tail"] = err[-800:] if err else ""
            if durations:
                cmd["slowest_durations"] = durations[:30]
    text = json.dumps(receipt, indent=2, sort_keys=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)

    bad = [
        r for r in results if r.returncode != 0 and not r.name.startswith("collect:browser_smoke")
    ]
    if bad:
        print(
            f"{len(bad)} command(s) exited non-zero: " + ", ".join(r.name for r in bad),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
