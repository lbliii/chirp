"""Fail a PR that claims to *close* an issue without an executable acceptance test.

The forcing function of the backlog-truth machinery (see
``docs/backlog-automation.md``): if a pull request body says ``Closes #143``,
there must be at least one ``@pytest.mark.issue(143)`` test in the tree. This
turns "done" into a derived fact at the moment work ships, instead of a claim a
human reconciles weeks later — the exact drift that left 13 epics open after
their work had merged.

Not every issue has a testable acceptance criterion (positioning, pure docs).
Those PRs declare an explicit, auditable exemption in the body::

    Acceptance: n/a (docs-only)

Design constraints (mirrors ``scripts/check_roadmap_staleness.py``): stdlib
only, no network, returns 0/1, prints an actionable message. The PR body is
supplied out-of-band (``--body-file``, ``--body``, ``$PR_BODY`` env, or stdin)
so the check never calls the GitHub API.

Usage::

    PR_BODY="$PR_BODY" python scripts/check_closure_acceptance.py
    python scripts/check_closure_acceptance.py --body-file pr_body.txt
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Let this script import its co-located sibling whether run as
# ``python scripts/x.py`` (sys.path[0] == scripts/) or imported in a test.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue_coverage import collect_issue_tests

# GitHub's issue-closing keywords (https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue).
_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[:\s]+#(\d+)",
    re.IGNORECASE,
)
# An auditable "this issue has no testable acceptance criterion" escape hatch.
_EXEMPT = re.compile(
    r"^\s*acceptance\s*:\s*(n/?a|none|not applicable)\b", re.IGNORECASE | re.MULTILINE
)


def extract_closing_issues(body: str) -> set[int]:
    """Issue numbers the PR body declares it will close via a closing keyword."""
    return {int(m) for m in _CLOSING.findall(body or "")}


def is_exempt(body: str) -> bool:
    """True when the body carries an explicit ``Acceptance: n/a`` declaration."""
    return bool(_EXEMPT.search(body or ""))


def _read_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    if args.body_file is not None:
        return Path(args.body_file).read_text(encoding="utf-8")
    env = os.environ.get("PR_BODY")
    if env is not None:
        return env
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body", help="PR body text (overrides other sources)")
    parser.add_argument("--body-file", help="path to a file containing the PR body")
    args = parser.parse_args(argv)

    body = _read_body(args)
    closing = extract_closing_issues(body)

    if not closing:
        print("No 'Closes #N' linkage in the PR body — nothing to gate.")
        return 0

    if is_exempt(body):
        print(
            "PR declares 'Acceptance: n/a' — closure-acceptance gate skipped for "
            + ", ".join(f"#{n}" for n in sorted(closing))
        )
        return 0

    coverage = collect_issue_tests()
    missing = sorted(n for n in closing if n not in coverage)
    if missing:
        joined = ", ".join(f"#{n}" for n in missing)
        print(
            f"::error::This PR claims to close {joined} but no acceptance test exists.\n"
            f"Add a test decorated with @pytest.mark.issue(N) that proves the issue's "
            f"acceptance criteria, or — if the issue has no testable criterion (docs / "
            f"positioning) — add a line to the PR body:\n"
            f"    Acceptance: n/a (reason)\n"
            f"See docs/backlog-automation.md."
        )
        return 1

    proven = ", ".join(f"#{n}" for n in sorted(closing))
    print(f"Acceptance tests present for {proven}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
