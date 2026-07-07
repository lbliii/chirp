#!/usr/bin/env python3
"""Run and retain Chirp's pinned upstream htmx 4 migration inventory."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

HTMX_VERSION = "4.0.0-beta5"
COMMAND = ("npx", "--yes", f"htmx.org@{HTMX_VERSION}", "upgrade-check", "--")
SUPPORTED_EXTENSIONS = frozenset(
    {".html", ".php", ".js", ".ts", ".jinja", ".jinja2", ".j2", ".erb", ".hbs"}
)
EXCLUDED_DIRECTORIES = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "node_modules", "ovrtx"}
)
_FINDING = re.compile(r"^(.*):(\d+): \[([^]]+)] (.*)$")
_SUMMARY = re.compile(r"Found (\d+) issue\(s\) in (\d+) of (\d+) file\(s\)\.")


@dataclass(frozen=True, slots=True)
class UpgradeFinding:
    """One normalized line from the upstream checker."""

    path: str
    line: int
    category: str
    message: str
    surface: str


def classify_surface(path: str) -> str:
    """Classify a finding by its repository-owned migration surface."""
    normalized = path.removeprefix("./")
    if normalized.startswith(("site/public/", "site/.bengal/")):
        return "generated"
    if normalized.startswith("src/chirp/"):
        return "framework"
    if normalized.startswith("examples/"):
        return "examples"
    if normalized.startswith("tests/"):
        return "tests"
    if normalized.startswith(("docs/", "site/content/")):
        return "documentation"
    return "other"


def parse_findings(output: str) -> list[UpgradeFinding]:
    """Parse stable ``file:line: [category] message`` output."""
    findings: list[UpgradeFinding] = []
    for line in output.splitlines():
        match = _FINDING.match(line)
        if match is None:
            continue
        path, line_number, category, message = match.groups()
        findings.append(
            UpgradeFinding(
                path=path.removeprefix("./"),
                line=int(line_number),
                category=category,
                message=message,
                surface=classify_surface(path),
            )
        )
    return findings


def collect_repository_files(root: Path) -> list[str]:
    """Collect supported repository files without local environments or caches."""
    paths: list[str] = []
    for directory, names, filenames in os.walk(root):
        names[:] = sorted(name for name in names if name not in EXCLUDED_DIRECTORIES)
        base = Path(directory)
        for filename in sorted(filenames):
            path = base / filename
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                paths.append(path.relative_to(root).as_posix())
    return paths


def build_report(
    findings: list[UpgradeFinding],
    stderr: str,
    *,
    root: Path,
) -> dict[str, object]:
    """Build deterministic JSON evidence from checker output."""
    summary = _SUMMARY.search(stderr)
    scanned_files = int(summary.group(3)) if summary is not None else None
    files_with_findings = (
        int(summary.group(2))
        if summary is not None
        else len({finding.path for finding in findings})
    )
    return {
        "schema": 1,
        "htmx_version": HTMX_VERSION,
        "command": [*COMMAND, "<repository-owned supported files>"],
        "scan_policy": {
            "extensions": sorted(SUPPORTED_EXTENSIONS),
            "excluded_directories": sorted(EXCLUDED_DIRECTORIES),
        },
        "root": str(root),
        "scanned_files": scanned_files,
        "files_with_findings": files_with_findings,
        "total_findings": len(findings),
        "categories": dict(sorted(Counter(item.category for item in findings).items())),
        "surfaces": dict(sorted(Counter(item.surface for item in findings).items())),
        "findings": [asdict(item) for item in findings],
    }


def run_checker(root: Path) -> dict[str, object]:
    """Run the optional upstream command; never import it into Chirp core."""
    files = collect_repository_files(root)
    if not files:
        msg = f"No supported htmx migration files found under {root}"
        raise RuntimeError(msg)
    command = [*COMMAND, *files]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
    except FileNotFoundError as exc:
        msg = (
            "Unable to run the optional htmx upgrade checker because 'npx' is unavailable. "
            "Install Node.js/npm or keep using app.check(), which has no Node dependency."
        )
        raise RuntimeError(msg) from exc
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no command output"
        msg = f"Pinned htmx upgrade checker failed with exit {completed.returncode}: {detail}"
        raise RuntimeError(msg)
    if _SUMMARY.search(completed.stderr) is None:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no command output"
        msg = f"Pinned htmx upgrade checker returned no scan summary: {detail}"
        raise RuntimeError(msg)
    findings = parse_findings(completed.stdout)
    return build_report(findings, completed.stderr, root=root)


def _comparable(report: dict[str, object]) -> dict[str, object]:
    return {
        key: report.get(key)
        for key in (
            "htmx_version",
            "scanned_files",
            "files_with_findings",
            "total_findings",
            "categories",
            "surfaces",
            "findings",
        )
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, help="write the normalized JSON report")
    parser.add_argument("--check", type=Path, help="fail when a retained JSON report has drifted")
    args = parser.parse_args(argv)

    try:
        report = run_checker(args.root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2, sort_keys=False) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    if args.check is not None:
        retained = json.loads(args.check.read_text(encoding="utf-8"))
        if _comparable(report) != _comparable(retained):
            print(f"htmx migration inventory differs from {args.check}", file=sys.stderr)
            return 1
    if args.output is None and args.check is None:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
