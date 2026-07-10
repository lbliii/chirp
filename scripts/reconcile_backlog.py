"""Re-derive backlog truth from git/GitHub and surface drift as labels + a report.

This productizes a one-off manual triage into a recurring sweep (see
``docs/backlog-automation.md``). The recurring failure mode it targets: PRs
merge faster than anyone reconciles the issues/epics that spawned them, so the
tracker rots (13 epics here were *fully shipped* yet still open). Instead of
trusting the tracker, this re-derives state every run from three signals:

1. **merged PRs** with explicit closing references or weak associations such
   as the ``issue-<N>-...`` branch convention,
2. the native GitHub **parent / sub-issue** relationship,
3. **executable acceptance** (``@pytest.mark.issue(N)`` coverage, via
   ``scripts/issue_coverage.py``),

and applies derived labels so a human sweeps labels in minutes rather than
re-triaging from zero:

- ``merged-pending-close`` — a non-epic issue a merged PR closes; verify & close.
- ``closure-candidate`` — a parent whose native children are all completed.
- ``needs-grooming`` — a leaf or parent violates the workable-backlog contract.
- ``needs-decomposition`` — an unblocked parent has no native children.
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
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue_coverage import collect_issue_tests

_CLOSING = re.compile(
    r"^\s*(?:[-*]\s*)?(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)
_MENTION = re.compile(r"(?<![/\w-])#(\d+)")
_BRANCH_ISSUE = re.compile(r"\bissue[-_/](\d+)\b", re.IGNORECASE)
_ADVANCES = re.compile(r"\badvances-epic\s*:\s*#(\d+)", re.IGNORECASE)

_PARENT_LABELS = frozenset({"saga", "epic", "implementation-epic"})
_BLOCKED_LABELS = frozenset({"blocked", "upstream-blocked"})
_RECONCILIATION_LABELS = frozenset(
    {"merged-pending-close", "stale-epic-review", "acceptance-tracked"}
)

# Derived labels this tool owns: name -> (color, description).
DERIVED_LABELS: dict[str, tuple[str, str]] = {
    "merged-pending-close": ("0e8a16", "A merged PR closes this issue; verify and close"),
    "stale-epic-review": ("fbca04", "Epic referenced by merged work; re-check children / close"),
    "acceptance-tracked": ("1d76db", "Has a @pytest.mark.issue acceptance test"),
    "closure-candidate": ("0e8a16", "All native child issues completed; verify parent gates"),
    "needs-grooming": ("d93f0b", "Backlog workability or hierarchy needs maintainer review"),
    "needs-decomposition": ("fbca04", "Unblocked parent has no native child issues"),
}


def pr_issue_links(pr: dict) -> tuple[set[int], set[int]]:
    """Return ``(closing, mentioned)`` issue numbers a merged PR points at.

    ``closing`` contains only explicit GitHub closing-keyword references.
    ``mentioned`` contains local bare references, ``Advances-Epic`` trailers,
    and the ``issue-<N>-`` branch convention. Associations are weak and never
    trigger a close recommendation on their own.
    """
    text = f"{pr.get('title', '')}\n{pr.get('body', '') or ''}"
    closing = {int(n) for n in _CLOSING.findall(text)}
    branch = pr.get("headRefName", "") or ""
    mentioned = {int(n) for n in _MENTION.findall(text)} - closing
    mentioned |= {int(n) for n in _ADVANCES.findall(text)}
    mentioned |= {int(n) for n in _BRANCH_ISSUE.findall(branch)}
    mentioned -= closing
    return closing, mentioned


def pr_work_claims(pr: dict) -> set[int]:
    """Return issues an open PR strongly signals it is actively addressing.

    Explicit closing references and the repository's ``issue-<N>-...`` branch
    convention are claims. Bare mentions and ``Advances-Epic`` trailers remain
    weak associations, so they do not hide otherwise workable leaves.
    """
    closing, _mentioned = pr_issue_links(pr)
    branch = pr.get("headRefName", "") or ""
    return closing | {int(number) for number in _BRANCH_ISSUE.findall(branch)}


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
        if "good first issue" in labels or issue.get("title", "").startswith("[GF]"):
            continue
        is_epic = bool(labels & _PARENT_LABELS)
        closes = sorted(set(closed_by.get(number, [])))
        mentions = sorted(set(mentioned_by.get(number, [])))
        has_tests = number in coverage

        desired: set[str] = set()
        reasons: list[str] = []
        if closes:
            joined = ", ".join(f"#{p}" for p in closes)
            if is_epic:
                desired.add("stale-epic-review")
                reasons.append(
                    f"epic referenced by merged PR(s) {joined} — re-check children / close"
                )
            else:
                desired.add("merged-pending-close")
                reasons.append(f"merged PR(s) {joined} close this — verify and close")
        elif mentions and not is_epic:
            joined = ", ".join(f"#{p}" for p in mentions)
            reasons.append(f"mentioned by merged PR(s) {joined} (weak signal — review)")
        if has_tests:
            desired.add("acceptance-tracked")
            reasons.append(f"has {len(coverage[number])} acceptance test(s)")

        current_owned = labels & _RECONCILIATION_LABELS
        add = sorted(desired - current_owned)
        remove = sorted(current_owned - desired)

        if add or remove or reasons:
            findings.append(
                {
                    "number": number,
                    "title": issue.get("title", ""),
                    "is_epic": is_epic,
                    "add_labels": add,
                    "remove_labels": remove,
                    "closed_by": closes,
                    "mentioned_by": mentions,
                    "has_tests": has_tests,
                    "reasons": reasons,
                }
            )
    return findings


def _is_open(issue: dict) -> bool:
    return str(issue.get("state", "OPEN")).upper() == "OPEN"


def _is_parent(issue: dict) -> bool:
    labels = {label_name(label) for label in issue.get("labels", [])}
    return bool(labels & _PARENT_LABELS) or bool(issue.get("subIssues"))


def _open_children(issue: dict) -> list[dict]:
    return [child for child in issue.get("subIssues", []) if _is_open(child)]


def _leaf_state(issue: dict) -> str:
    labels = {label_name(label) for label in issue.get("labels", [])}
    ready = "ready" in labels
    blocked = bool(labels & _BLOCKED_LABELS)
    open_blockers = [
        blocker
        for blocker in issue.get("blockedBy", [])
        if str(blocker.get("state", "OPEN")).upper() == "OPEN"
    ]
    if ready and (blocked or open_blockers):
        return "conflict"
    if ready:
        return "ready"
    if blocked:
        return "blocked"
    return "missing"


def derive_workability_findings(open_issues: list[dict]) -> list[dict]:
    """Return graph/work-state findings for the open non-contributor backlog."""
    by_number = {issue["number"]: issue for issue in open_issues}
    findings: list[dict] = []

    def descendants(number: int, visiting: frozenset[int] = frozenset()) -> set[str]:
        if number in visiting:
            return {"conflict"}
        issue = by_number[number]
        children = _open_children(issue)
        if not children:
            return {_leaf_state(issue)}
        states: set[str] = set()
        for child in children:
            child_number = child["number"]
            if child_number in by_number:
                states |= descendants(child_number, visiting | {number})
            else:
                states.add(_leaf_state(child))
        return states

    for issue in open_issues:
        labels = {label_name(label) for label in issue.get("labels", [])}
        if "good first issue" in labels or issue.get("title", "").startswith("[GF]"):
            continue
        number = issue["number"]
        children = issue.get("subIssues", [])
        open_children = _open_children(issue)
        is_parent = _is_parent(issue)
        codes: list[str] = []
        reasons: list[str] = []

        if is_parent:
            if "ready" in labels:
                codes.append("ready-parent")
                reasons.append("ready is reserved for executable leaves")
            if not children and not (labels & _BLOCKED_LABELS):
                codes.append("parent-no-children")
                reasons.append("unblocked parent has no native sub-issues")
            elif children and not open_children:
                state_reasons = {str(child.get("stateReason") or "").upper() for child in children}
                if state_reasons <= {"COMPLETED", ""}:
                    codes.append("closure-candidate")
                    reasons.append("all native child issues are closed as completed")
                else:
                    codes.append("closed-not-planned-child")
                    reasons.append("all children are closed but at least one was not planned")
            elif open_children:
                states = descendants(number)
                if "ready" not in states and states != {"blocked"}:
                    codes.append("parent-no-workable-leaf")
                    reasons.append("no open descendant is ready and not every path is blocked")
        else:
            state = _leaf_state(issue)
            if state == "missing":
                codes.append("work-state-missing")
                reasons.append("leaf has neither ready nor blocked state")
            elif state == "conflict":
                codes.append("work-state-conflict")
                reasons.append("leaf is ready while a blocked state or open blocker remains")
            if "blocked" in labels and not issue.get("blockedBy"):
                codes.append("blocked-without-dependency")
                reasons.append("internally blocked leaf has no native blocked-by relationship")

        if codes:
            desired: set[str] = set()
            if "closure-candidate" in codes:
                desired.add("closure-candidate")
            if "parent-no-children" in codes:
                desired.add("needs-decomposition")
            if any(
                code
                in {
                    "ready-parent",
                    "parent-no-workable-leaf",
                    "work-state-missing",
                    "work-state-conflict",
                    "blocked-without-dependency",
                    "closed-not-planned-child",
                }
                for code in codes
            ):
                desired.add("needs-grooming")
            current = labels & {"closure-candidate", "needs-decomposition", "needs-grooming"}
            findings.append(
                {
                    "number": number,
                    "title": issue.get("title", ""),
                    "codes": codes,
                    "reasons": reasons,
                    "add_labels": sorted(desired - current),
                    "remove_labels": sorted(current - desired),
                }
            )
        else:
            current = labels & {"closure-candidate", "needs-decomposition", "needs-grooming"}
            if current:
                findings.append(
                    {
                        "number": number,
                        "title": issue.get("title", ""),
                        "codes": [],
                        "reasons": ["previous workability finding is now resolved"],
                        "add_labels": [],
                        "remove_labels": sorted(current),
                    }
                )
    return findings


def label_name(label: object) -> str:
    """Normalize a gh label (dict ``{name}`` or plain string) to its name."""
    if isinstance(label, dict):
        value = cast(dict[str, object], label)
        return str(value.get("name", ""))
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
            label_note = f" → add `{'`, `'.join(f['add_labels'])}`" if f["add_labels"] else ""
            if f.get("remove_labels"):
                label_note += f" → remove `{'`, `'.join(f['remove_labels'])}`"
            lines.append(f"- #{f['number']} {f['title']}{label_note} — {reason}")
        lines.append("")

    close_candidates = [f for f in findings if f["closed_by"] and not f["is_epic"]]
    epic_review = [f for f in findings if f["closed_by"] and f["is_epic"]]
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


def _gh_json(args: list[str]) -> Any:
    out = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if out.returncode:
        detail = out.stderr.strip() or out.stdout.strip() or "no diagnostic output"
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {detail}")
    return json.loads(out.stdout or "[]")


_ISSUES_QUERY = """
query BacklogIssues($owner:String!, $name:String!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    issues(first:100, after:$cursor, states:OPEN, orderBy:{field:CREATED_AT,direction:ASC}) {
      nodes {
        id databaseId number title body url state stateReason createdAt updatedAt
        labels(first:50) { nodes { name } }
        parent { number }
        subIssues(first:100) {
          nodes { number title state stateReason labels(first:20) { nodes { name } } }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def _repo_name() -> str:
    value = _gh_json(["repo", "view", "--json", "nameWithOwner"])
    if not isinstance(value, dict) or not isinstance(value.get("nameWithOwner"), str):
        raise TypeError("gh repo view returned no nameWithOwner")
    return cast(str, value["nameWithOwner"])


def _normalize_issue(node: dict) -> dict:
    return {
        **{
            key: node.get(key)
            for key in (
                "id",
                "databaseId",
                "number",
                "title",
                "body",
                "url",
                "state",
                "stateReason",
                "createdAt",
                "updatedAt",
            )
        },
        "labels": [item["name"] for item in node.get("labels", {}).get("nodes", [])],
        "parent": node.get("parent"),
        "subIssues": [
            {
                **{key: child.get(key) for key in ("number", "title", "state", "stateReason")},
                "labels": [item["name"] for item in child.get("labels", {}).get("nodes", [])],
            }
            for child in node.get("subIssues", {}).get("nodes", [])
        ],
    }


def _fetch_blockers(repository: str, number: int) -> list[dict]:
    value = _gh_json(
        [
            "api",
            f"repos/{repository}/issues/{number}/dependencies/blocked_by?per_page=100",
            "--paginate",
            "--slurp",
        ]
    )
    pages = value if isinstance(value, list) else []
    rows = (
        [item for page in pages for item in page]
        if pages and all(isinstance(page, list) for page in pages)
        else pages
    )
    return [{"number": row["number"], "title": row["title"], "state": row["state"]} for row in rows]


def fetch_open_issues(
    limit: int = 1000,
    repository: str | None = None,
    *,
    include_dependencies: bool = False,
) -> list[dict]:
    repository = repository or _repo_name()
    owner, name = repository.split("/", 1)
    cursor: str | None = None
    issues: list[dict] = []
    while len(issues) < limit:
        args = [
            "api",
            "graphql",
            "-f",
            f"query={_ISSUES_QUERY}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
        ]
        if cursor is not None:
            args += ["-F", f"cursor={cursor}"]
        payload = _gh_json(args)
        if not isinstance(payload, dict):
            raise TypeError("GitHub GraphQL returned a non-object response")
        if payload.get("errors"):
            raise RuntimeError(f"GitHub GraphQL errors: {payload['errors']}")
        connection = payload["data"]["repository"]["issues"]
        issues.extend(_normalize_issue(node) for node in connection["nodes"])
        page = connection["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
        if not cursor:
            raise RuntimeError("GitHub reported another issue page without an end cursor")
    issues = issues[:limit]
    if include_dependencies:
        for issue in issues:
            labels = {label_name(label) for label in issue.get("labels", [])}
            issue["blockedBy"] = (
                _fetch_blockers(repository, issue["number"])
                if labels & (_BLOCKED_LABELS | {"ready"})
                else []
            )
    return issues


def fetch_merged_prs(limit: int) -> list[dict]:
    value = _gh_json(
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
    if not isinstance(value, list):
        raise TypeError("gh pr list returned a non-list response")
    return cast(list[dict], value)


def ensure_labels() -> None:
    for name, (color, desc) in DERIVED_LABELS.items():
        subprocess.run(
            ["gh", "label", "create", name, "--color", color, "--description", desc, "--force"],
            check=True,
            capture_output=True,
            text=True,
        )


def apply_labels(findings: list[dict]) -> int:
    applied = 0
    for f in findings:
        if not f.get("add_labels") and not f.get("remove_labels"):
            continue
        cmd = ["gh", "issue", "edit", str(f["number"])]
        for label in f.get("add_labels", []):
            cmd += ["--add-label", label]
        for label in f.get("remove_labels", []):
            cmd += ["--remove-label", label]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        applied += 1
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="ensure + attach derived labels")
    parser.add_argument("--limit", type=int, default=1000, help="max issues/PRs to scan")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--snapshot", help="write the normalized issue graph as JSON")
    parser.add_argument(
        "--report-workability", action="store_true", help="include hierarchy/work-state findings"
    )
    parser.add_argument(
        "--with-dependencies", action="store_true", help="include native blocked-by relationships"
    )
    args = parser.parse_args(argv)

    open_issues = fetch_open_issues(args.limit, include_dependencies=args.with_dependencies)
    merged_prs = fetch_merged_prs(args.limit)
    coverage = collect_issue_tests()
    findings = derive_findings(open_issues, merged_prs, coverage)
    workability = derive_workability_findings(open_issues)

    if args.snapshot:
        Path(args.snapshot).write_text(json.dumps(open_issues, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"reconciliation": findings, "workability": workability}, indent=2))
        return 0

    print(render_report(findings, coverage))
    if args.report_workability:
        print("\n# Backlog workability\n")
        if not workability:
            print("_No non-GF workability violations._")
        for finding in workability:
            changes = [
                *(f"+{label}" for label in finding["add_labels"]),
                *(f"-{label}" for label in finding["remove_labels"]),
            ]
            suffix = f" ({', '.join(changes)})" if changes else ""
            print(
                f"- #{finding['number']} {finding['title']}{suffix}: {'; '.join(finding['reasons'])}"
            )

    if args.apply:
        ensure_labels()
        applied = apply_labels([*findings, *workability])
        print(f"\n_Applied derived labels to {applied} issue(s)._")
    return 0


if __name__ == "__main__":
    sys.exit(main())
