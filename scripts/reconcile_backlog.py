"""Re-derive backlog truth from git/GitHub and surface drift as labels + a report.

This productizes a one-off manual triage into a recurring sweep (see
``docs/backlog-automation.md``). The recurring failure mode it targets: PRs
merge faster than anyone reconciles the issues/epics that spawned them, so the
tracker rots (13 epics here were *fully shipped* yet still open). Instead of
trusting the tracker, this re-derives state every run from three signals:

1. **merged PRs** that close/reference an issue (closing keywords + the
   ``issue-<N>-...`` branch convention),
2. the **sub-issue / epic** relationship (the ``epic`` label),
3. **executable acceptance** (``@pytest.mark.issue(N)`` coverage, via
   ``scripts/issue_coverage.py``),

and applies derived labels so a human sweeps labels in minutes rather than
re-triaging from zero:

- ``merged-pending-close`` — a non-epic issue a merged PR closes; verify & close.
- ``stale-epic-review`` — an epic whose work merged; re-check children / close.
- ``acceptance-tracked`` — the issue has an executable acceptance test.

Read-only by default (prints a Markdown report to stdout); ``--apply`` ensures
the labels exist and attaches them. Network/``gh`` are only used by the I/O
helpers; the derivation logic is pure and unit-tested.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue_coverage import collect_issue_tests

_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[:\s]+#(\d+)",
    re.IGNORECASE,
)
_MENTION = re.compile(r"#(\d+)")
_BRANCH_ISSUE = re.compile(r"\bissue[-_/](\d+)\b", re.IGNORECASE)

# Derived labels this tool owns: name -> (color, description).
DERIVED_LABELS: dict[str, tuple[str, str]] = {
    "merged-pending-close": ("0e8a16", "A merged PR closes this issue; verify and close"),
    "stale-epic-review": ("fbca04", "Epic referenced by merged work; re-check children / close"),
    "acceptance-tracked": ("1d76db", "Has a @pytest.mark.issue acceptance test"),
}


def pr_issue_links(pr: dict) -> tuple[set[int], set[int]]:
    """Return ``(closing, mentioned)`` issue numbers a merged PR points at.

    ``closing`` = explicit closing-keyword references plus the ``issue-<N>-``
    branch convention (a strong "this PR is for issue N" signal). ``mentioned``
    = any other ``#N`` in the title/body. Mentions are weak and never trigger a
    close recommendation on their own.
    """
    text = f"{pr.get('title', '')}\n{pr.get('body', '') or ''}"
    closing = {int(n) for n in _CLOSING.findall(text)}
    branch = pr.get("headRefName", "") or ""
    closing |= {int(n) for n in _BRANCH_ISSUE.findall(branch)}
    mentioned = {int(n) for n in _MENTION.findall(text)} - closing
    return closing, mentioned


def derive_findings(
    open_issues: list[dict],
    merged_prs: list[dict],
    coverage: dict[int, list[str]],
) -> list[dict]:
    """Pure: map open issues + merged PRs + acceptance coverage to findings.

    Each finding is ``{number, title, is_epic, add_labels, closed_by,
    mentioned_by, has_tests, reasons}``. Only issues with at least one signal
    are returned.
    """
    closed_by: dict[int, list[int]] = {}
    mentioned_by: dict[int, list[int]] = {}
    for pr in merged_prs:
        closing, mentioned = pr_issue_links(pr)
        for n in closing:
            closed_by.setdefault(n, []).append(pr["number"])
        for n in mentioned:
            mentioned_by.setdefault(n, []).append(pr["number"])

    findings: list[dict] = []
    for issue in open_issues:
        number = issue["number"]
        labels = {label_name(label) for label in issue.get("labels", [])}
        is_epic = "epic" in labels
        closes = sorted(set(closed_by.get(number, [])))
        mentions = sorted(set(mentioned_by.get(number, [])))
        has_tests = number in coverage

        add: list[str] = []
        reasons: list[str] = []
        if closes:
            joined = ", ".join(f"#{p}" for p in closes)
            if is_epic:
                add.append("stale-epic-review")
                reasons.append(
                    f"epic referenced by merged PR(s) {joined} — re-check children / close"
                )
            else:
                add.append("merged-pending-close")
                reasons.append(f"merged PR(s) {joined} close this — verify and close")
        elif mentions and not is_epic:
            joined = ", ".join(f"#{p}" for p in mentions)
            reasons.append(f"mentioned by merged PR(s) {joined} (weak signal — review)")
        if has_tests:
            add.append("acceptance-tracked")
            reasons.append(f"has {len(coverage[number])} acceptance test(s)")

        # Only keep an existing label off the add-list (idempotency happens at apply time,
        # but we also do not "add" a label that won't change anything for the report).
        add = [label for label in add if label not in labels]

        if add or reasons:
            findings.append(
                {
                    "number": number,
                    "title": issue.get("title", ""),
                    "is_epic": is_epic,
                    "add_labels": add,
                    "closed_by": closes,
                    "mentioned_by": mentions,
                    "has_tests": has_tests,
                    "reasons": reasons,
                }
            )
    return findings


def label_name(label: object) -> str:
    """Normalize a gh label (dict ``{name}`` or plain string) to its name."""
    if isinstance(label, dict):
        return str(label.get("name", ""))
    return str(label)


def render_report(findings: list[dict], coverage: dict[int, list[str]]) -> str:
    """Render a Markdown reconciliation report (also suitable for a CI summary)."""
    lines = ["# Backlog reconciliation", ""]

    def section(title: str, rows: list[dict]) -> None:
        lines.append(f"## {title} ({len(rows)})")
        if not rows:
            lines.append("_none_")
            lines.append("")
            return
        for f in rows:
            reason = "; ".join(f["reasons"])
            label_note = f" → `{'`, `'.join(f['add_labels'])}`" if f["add_labels"] else ""
            lines.append(f"- #{f['number']} {f['title']}{label_note} — {reason}")
        lines.append("")

    close_candidates = [f for f in findings if "merged-pending-close" in f["add_labels"]]
    epic_review = [f for f in findings if "stale-epic-review" in f["add_labels"]]
    tracked = [f for f in findings if f["has_tests"]]
    weak = [f for f in findings if not f["closed_by"] and f["mentioned_by"] and not f["is_epic"]]

    section("Merged — pending close", close_candidates)
    section("Epics to re-review", epic_review)
    section("Mentioned by merged PRs (weak)", weak)
    lines.append(f"## Acceptance-tracked issues ({len(tracked)})")
    if tracked:
        lines.extend(f"- #{f['number']} ({len(coverage[f['number']])} test(s))" for f in tracked)
    else:
        lines.append(
            "_No open issue yet carries a `@pytest.mark.issue` acceptance test. "
            "Adopt the marker as issues are worked — see docs/backlog-automation.md._"
        )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# I/O helpers (the only part that touches the network / gh).
# --------------------------------------------------------------------------- #


def _gh_json(args: list[str]) -> list[dict]:
    out = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout or "[]")


def fetch_open_issues(limit: int) -> list[dict]:
    return _gh_json(
        ["issue", "list", "--state", "open", "--limit", str(limit), "--json", "number,title,labels"]
    )


def fetch_merged_prs(limit: int) -> list[dict]:
    return _gh_json(
        [
            "pr",
            "list",
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--json",
            "number,title,body,headRefName",
        ]
    )


def ensure_labels() -> None:
    for name, (color, desc) in DERIVED_LABELS.items():
        subprocess.run(
            ["gh", "label", "create", name, "--color", color, "--description", desc, "--force"],
            check=False,
            capture_output=True,
            text=True,
        )


def apply_labels(findings: list[dict]) -> None:
    for f in findings:
        if not f["add_labels"]:
            continue
        cmd = ["gh", "issue", "edit", str(f["number"])]
        for label in f["add_labels"]:
            cmd += ["--add-label", label]
        subprocess.run(cmd, check=False, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="ensure + attach derived labels")
    parser.add_argument("--limit", type=int, default=300, help="max issues/PRs to scan")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    open_issues = fetch_open_issues(args.limit)
    merged_prs = fetch_merged_prs(args.limit)
    coverage = collect_issue_tests()
    findings = derive_findings(open_issues, merged_prs, coverage)

    if args.json:
        print(json.dumps(findings, indent=2))
        return 0

    print(render_report(findings, coverage))

    if args.apply:
        ensure_labels()
        apply_labels(findings)
        applied = sum(1 for f in findings if f["add_labels"])
        print(f"\n_Applied derived labels to {applied} issue(s)._")
    return 0


if __name__ == "__main__":
    sys.exit(main())
