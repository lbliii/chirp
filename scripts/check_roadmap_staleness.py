"""Fail if a roadmap file makes a static "no open GitHub issues" assertion.

`ROADMAP.md` once carried a date-stamped line such as::

    Open GitHub issues checked on 2026-05-30: none.

That claim goes stale silently: the moment a new issue is filed the roadmap
misleads any reader (or agent) who trusts it. This guard scans roadmap files
for an *unqualified* "no open issues / none open" assertion and fails when one
is present, steering authors toward pointing at the live GitHub backlog instead
of baking a count into version control.

Design constraints (see issue #199):

- **Stdlib only, returns 0/1, prints an actionable message** — mirrors
  ``scripts/check_changelog_fragments.py`` and runs as a local pre-commit hook.
- **No hard network dependency.** The default check is a pure static-regex
  assertion so offline contributors and air-gapped CI are never blocked. When
  ``gh`` is on ``PATH`` *and* authenticated, ``--with-gh`` additionally fails if
  the file claims "none open" while the live backlog actually has open issues;
  a missing/unauthenticated ``gh`` (or any network error) is treated as a skip,
  not a failure.

Qualified, historical snapshots are allowed: a line that says "none open *as of*
…" or otherwise carries a ``snapshot`` / ``point-in-time`` / ``as of`` marker is
understood to be a dated reading, not a live claim, and does not fail the guard.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

# Matches an assertion that there are currently no open issues, e.g.
#   "Open GitHub issues checked on 2026-05-30: none"
#   "GitHub issues: none open"
# We deliberately keep this narrow: it must mention GitHub issues *and* a
# "none"/"no open" verdict on the same line.
_STALE_CLAIM = re.compile(
    r"(?:open\s+github\s+issues\b.*\bnone\b)"
    r"|(?:github\s+issues\b.*\bnone\s+open\b)"
    r"|(?:\bno\s+open\b.*\bgithub\s+issues\b)",
    re.IGNORECASE,
)

# A line carrying any of these markers is a dated/historical snapshot, not a
# live claim, and is exempt.
_SNAPSHOT_MARKER = re.compile(
    r"snapshot|point-in-time|point in time|\bas of\b|authoritative|do not trust"
    r"|historical|research pass",
    re.IGNORECASE,
)

# Files guarded by default when invoked without explicit paths.
_DEFAULT_FILES = ("ROADMAP.md", "plan/roadmap.md")


def _stale_lines(path: Path) -> list[tuple[int, str]]:
    """Return (line_number, line) for each unqualified stale claim in *path*."""
    if not path.is_file():
        return []
    bad: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if _STALE_CLAIM.search(line) and not _SNAPSHOT_MARKER.search(line):
            bad.append((lineno, line.strip()))
    return bad


def _gh_has_open_issues() -> bool | None:
    """Return True/False if ``gh`` can report open issues, else None (skip).

    None means we could not reach a trustworthy answer — gh missing, not
    authenticated, offline, or any subprocess error — so the caller treats it
    as "unknown" and does not fail on the live-count basis.
    """
    gh = shutil.which("gh")
    if gh is None:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 — static args, gh resolved from PATH
            [gh, "issue", "list", "--state", "open", "--json", "number", "--limit", "1"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.SubprocessError, OSError:
        return None
    if proc.returncode != 0:
        return None
    # Non-empty JSON array (anything past "[]") means at least one open issue.
    return proc.stdout.strip() not in ("", "[]")


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--with-gh"]
    with_gh = "--with-gh" in argv

    paths = [Path(a) for a in args] if args else [Path(p) for p in _DEFAULT_FILES]

    stale: list[tuple[Path, int, str]] = []
    for path in paths:
        for lineno, line in _stale_lines(path):
            stale.append((path, lineno, line))

    if stale:
        print("error: roadmap files must not statically assert 'no open GitHub issues'.")
        print("       That claim goes stale silently. Point at the live backlog instead")
        print("       (https://github.com/lbliii/chirp/issues) or mark the line as a")
        print("       dated snapshot ('... none open as of <date>').")
        print()
        for path, lineno, line in stale:
            print(f"  {path}:{lineno}: {line[:100]}")
        return 1

    if with_gh:
        # Optional, network-dependent reinforcement. Absence is a skip, never a
        # failure, so offline contributors and air-gapped CI are not blocked.
        has_open = _gh_has_open_issues()
        if has_open is None:
            print("note: gh unavailable/unauthenticated; skipped live-backlog cross-check.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
