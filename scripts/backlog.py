"""Audit, recommend, explain, validate, and safely apply backlog work.

The live GitHub issue graph remains authoritative. Plans are ephemeral JSON
input: validation is pure, apply is dry-run by default, and every remote create
or comment carries a stable marker so interrupted runs can resume safely.
Recommendations are read-only, eligibility-gated, and deterministically ranked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue_coverage import collect_issue_tests
from reconcile_backlog import (
    derive_findings,
    derive_workability_findings,
    fetch_merged_prs,
    fetch_open_issues,
    label_name,
    pr_work_claims,
    render_report,
)

_PLAN_KEYS = frozenset(
    {"version", "repository", "baseline_sha", "generated_at", "preconditions", "actions"}
)
_ACTION_KEYS: dict[str, frozenset[str]] = {
    "create": frozenset(
        {
            "id",
            "kind",
            "issue_kind",
            "title",
            "labels",
            "parent",
            "blocked_by",
            "standalone",
            "spec",
            "idempotency_key",
        }
    ),
    "edit": frozenset(
        {
            "id",
            "kind",
            "issue",
            "title",
            "body",
            "add_labels",
            "remove_labels",
            "parent",
            "blocked_by",
            "comment",
            "comment_key",
        }
    ),
    "comment": frozenset({"id", "kind", "issue", "comment", "comment_key"}),
    "close": frozenset({"id", "kind", "issue", "reason", "evidence", "comment", "comment_key"}),
}
_SPEC_KEYS = frozenset(
    {
        "outcome",
        "immediate_action",
        "context",
        "scope",
        "boundaries",
        "proof",
        "acceptance",
        "collateral",
        "blocked_until",
    }
)
_SPEC_REQUIRED = frozenset(
    {"outcome", "immediate_action", "scope", "boundaries", "proof", "acceptance", "collateral"}
)
_ISSUE_KINDS = frozenset({"saga", "epic", "task", "rfc", "bug"})
_LEAF_KINDS = frozenset({"task", "rfc", "bug"})
_PARENT_KINDS = frozenset({"saga", "epic"})
_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
_BLOCKED_LABELS = frozenset({"blocked", "upstream-blocked"})
_DECISION_GATE_LABELS = frozenset(
    {"awaiting-decision", "decision-needed", "decision-required", "needs-decision"}
)
_PARENT_LABELS = frozenset({"saga", "epic", "implementation-epic"})
_KNOWN_AREAS = frozenset(
    {
        "ai",
        "app",
        "cache",
        "cli",
        "contracts",
        "data",
        "docs",
        "ext",
        "http",
        "i18n",
        "markdown",
        "middleware",
        "pages",
        "realtime",
        "routing",
        "security",
        "server",
        "templating",
        "testing",
        "tools",
        "validation",
    }
)
_CONTROL_LABELS = frozenset(
    {
        "blocked",
        "bug",
        "acceptance-tracked",
        "closure-candidate",
        "decision",
        "epic",
        "good first issue",
        "implementation-epic",
        "merged-pending-close",
        "needs-decomposition",
        "needs-grooming",
        "ready",
        "rfc",
        "saga",
        "stale-epic-review",
        "task",
        "upstream-blocked",
    }
)
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "unprioritized": 4}
_MARKER = re.compile(r"<!-- chirp-backlog-key:([a-z0-9][a-z0-9._-]{2,79}) -->")
_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_ACTIONS = 200
_MAX_BODY = 60_000


class BacklogPlanError(ValueError):
    """Raised when a plan or its remote preconditions are unsafe."""


@dataclass(frozen=True, slots=True)
class WorkAssessment:
    """Stable, serializable explanation of whether an issue is workable now."""

    number: int
    title: str
    url: str
    kind: str
    labels: tuple[str, ...]
    eligible: bool
    checks: tuple[tuple[str, bool, str], ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    priority: str
    effective_priority: str
    parent_chain: tuple[int, ...]
    blocked_by: tuple[int, ...]
    open_prs: tuple[tuple[int, str, bool], ...]
    unlocks: tuple[int, ...]
    areas: tuple[str, ...]
    created_at: str
    immediate_action: str
    required_proof: str
    acceptance: str

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["checks"] = [
            {"name": name, "passed": passed, "detail": detail}
            for name, passed, detail in self.checks
        ]
        value["open_prs"] = [
            {"number": number, "url": url, "draft": draft} for number, url, draft in self.open_prs
        ]
        return value


def _json_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def load_plan(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise BacklogPlanError("plan root must be a JSON object")
    return value


def _ref(value: object) -> bool:
    return (isinstance(value, int) and value > 0) or (
        isinstance(value, str) and bool(_KEY.fullmatch(value))
    )


def _create_graph(actions: list[dict[str, Any]]) -> dict[str, set[str]]:
    ids = {action["id"] for action in actions if action.get("kind") == "create"}
    graph = {action_id: set() for action_id in ids}
    for action in actions:
        if action["kind"] != "create":
            continue
        refs = [action.get("parent"), *action.get("blocked_by", [])]
        graph[action["id"]] |= {ref for ref in refs if isinstance(ref, str) and ref in ids}
    return graph


def _topological_create_ids(actions: list[dict[str, Any]]) -> list[str]:
    graph = _create_graph(actions)
    ordered: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(node: str) -> None:
        if node in permanent:
            return
        if node in temporary:
            raise BacklogPlanError(f"plan-local parent/blocker cycle includes {node!r}")
        temporary.add(node)
        for dependency in sorted(graph[node]):
            visit(dependency)
        temporary.remove(node)
        permanent.add(node)
        ordered.append(node)

    for node in sorted(graph):
        visit(node)
    return ordered


def validate_plan(plan: dict[str, Any]) -> list[str]:
    """Validate an ephemeral plan without touching git or GitHub."""
    errors: list[str] = []
    unknown = set(plan) - _PLAN_KEYS
    if unknown:
        errors.append(f"unknown plan fields: {', '.join(sorted(unknown))}")
    if plan.get("version") != 1:
        errors.append("plan version must be 1")
    repository = plan.get("repository")
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        errors.append("repository must be owner/name")
    preconditions = plan.get("preconditions", {})
    if not isinstance(preconditions, dict):
        errors.append("preconditions must be an object keyed by issue number")
        preconditions = {}
    else:
        for issue, value in preconditions.items():
            if not issue.isdigit() or not isinstance(value, dict):
                errors.append("each precondition must map a numeric issue key to an object")
                continue
            if set(value) - {"updated_at", "body_sha256"}:
                errors.append(f"precondition #{issue} has unknown fields")
            if not isinstance(value.get("updated_at"), str):
                errors.append(f"precondition #{issue} requires updated_at")

    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        errors.append("actions must be a non-empty list")
        return errors
    if len(actions) > _MAX_ACTIONS:
        errors.append(f"plan exceeds {_MAX_ACTIONS} actions")
    action_ids: set[str] = set()
    marker_keys: set[str] = set()
    local_kinds: dict[str, str] = {}

    for index, action in enumerate(actions):
        where = f"actions[{index}]"
        if not isinstance(action, dict):
            errors.append(f"{where} must be an object")
            continue
        action = cast(dict[str, Any], action)
        kind = action.get("kind")
        if kind not in _ACTION_KEYS:
            errors.append(f"{where}.kind must be create, edit, comment, or close")
            continue
        unknown_action = set(action) - _ACTION_KEYS[kind]
        if unknown_action:
            errors.append(f"{where} has unknown fields: {', '.join(sorted(unknown_action))}")
        action_id = action.get("id")
        if not isinstance(action_id, str) or not _KEY.fullmatch(action_id):
            errors.append(f"{where}.id must be a stable lowercase key")
            continue
        if action_id in action_ids:
            errors.append(f"duplicate action id {action_id!r}")
        action_ids.add(action_id)

        if kind == "create":
            issue_kind = action.get("issue_kind")
            if issue_kind not in _ISSUE_KINDS:
                errors.append(f"{where}.issue_kind is invalid")
                continue
            local_kinds[action_id] = issue_kind
            title = action.get("title")
            labels = action.get("labels")
            spec = action.get("spec")
            key = action.get("idempotency_key")
            if not isinstance(title, str) or not title.strip() or len(title) > 256:
                errors.append(f"{where}.title must be 1-256 characters")
            if isinstance(title, str) and title.startswith("[GF]"):
                errors.append(f"{where} may not create good-first work")
            if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
                errors.append(f"{where}.labels must be a string list")
                labels = []
            label_set = set(labels)
            if len(label_set) != len(labels):
                errors.append(f"{where}.labels contains duplicates")
            if "good first issue" in label_set:
                errors.append(f"{where} may not create good-first work")
            priorities = label_set & _PRIORITIES
            if issue_kind in _LEAF_KINDS and len(priorities) != 1:
                errors.append(f"{where} leaf requires exactly one P0-P3 label")
            ready = "ready" in label_set
            blocked = bool(label_set & _BLOCKED_LABELS)
            if issue_kind in _PARENT_KINDS and ready:
                errors.append(f"{where} parent may not carry ready")
            if issue_kind in _LEAF_KINDS and ready == blocked:
                errors.append(f"{where} leaf must be exactly one of ready or blocked")
            if ready and action.get("blocked_by"):
                errors.append(f"{where} ready leaf may not have blockers")
            parent = action.get("parent")
            if parent is not None and not _ref(parent):
                errors.append(f"{where}.parent must be an issue number or action id")
            if issue_kind == "task" and parent is None and not action.get("standalone", False):
                errors.append(f"{where} task requires parent or standalone=true")
            blocked_by = action.get("blocked_by", [])
            if not isinstance(blocked_by, list) or not all(_ref(ref) for ref in blocked_by):
                errors.append(f"{where}.blocked_by must contain issue numbers or action ids")
            if not isinstance(spec, dict):
                errors.append(f"{where}.spec must be an object")
            else:
                unknown_spec = set(spec) - _SPEC_KEYS
                missing_spec = _SPEC_REQUIRED - set(spec)
                if unknown_spec:
                    errors.append(
                        f"{where}.spec has unknown fields: {', '.join(sorted(unknown_spec))}"
                    )
                if missing_spec:
                    errors.append(f"{where}.spec is missing: {', '.join(sorted(missing_spec))}")
                errors.extend(
                    f"{where}.spec.{field} must be non-empty text"
                    for field in _SPEC_REQUIRED & set(spec)
                    if not isinstance(spec[field], str) or not spec[field].strip()
                )
                if blocked and not str(spec.get("blocked_until", "")).strip():
                    errors.append(f"{where} blocked work requires spec.blocked_until")
            if not isinstance(key, str) or not _KEY.fullmatch(key):
                errors.append(f"{where}.idempotency_key must be a stable lowercase key")
            elif key in marker_keys:
                errors.append(f"duplicate idempotency key {key!r}")
            else:
                marker_keys.add(key)
        else:
            issue = action.get("issue")
            if not isinstance(issue, int) or issue <= 0:
                errors.append(f"{where}.issue must be a positive issue number")
            comment = action.get("comment")
            comment_key = action.get("comment_key")
            if comment is not None:
                if not isinstance(comment, str) or not comment.strip():
                    errors.append(f"{where}.comment must be non-empty text")
                if not isinstance(comment_key, str) or not _KEY.fullmatch(comment_key):
                    errors.append(f"{where}.comment_key is required for idempotency")
                elif comment_key in marker_keys:
                    errors.append(f"duplicate idempotency key {comment_key!r}")
                else:
                    marker_keys.add(comment_key)
            if action.get("parent") is not None and not _ref(action["parent"]):
                errors.append(f"{where}.parent must be an issue number or action id")
            if "blocked_by" in action:
                refs = action["blocked_by"]
                if not isinstance(refs, list) or not all(_ref(ref) for ref in refs):
                    errors.append(f"{where}.blocked_by is invalid")
            if kind == "close":
                if action.get("reason") not in {"completed", "not_planned"}:
                    errors.append(f"{where}.reason must be completed or not_planned")
                if not isinstance(action.get("evidence"), str) or not action["evidence"].strip():
                    errors.append(f"{where}.evidence is required")
                if not action.get("comment"):
                    errors.append(f"{where}.comment is required to record the closure rationale")

    for action in actions:
        if not isinstance(action, dict):
            continue
        action = cast(dict[str, Any], action)
        parent = action.get("parent")
        if isinstance(parent, str) and parent not in local_kinds:
            errors.append(
                f"action {action.get('id')!r} references unknown create parent {parent!r}"
            )
        errors.extend(
            f"action {action.get('id')!r} references unknown create blocker {ref!r}"
            for ref in action.get("blocked_by", [])
            if isinstance(ref, str) and ref not in local_kinds
        )

    children_by_local_parent: dict[str, int] = {}
    for action in actions:
        parent = action.get("parent") if isinstance(action, dict) else None
        if isinstance(parent, str):
            children_by_local_parent[parent] = children_by_local_parent.get(parent, 0) + 1
    for action_id, issue_kind in local_kinds.items():
        if issue_kind not in _PARENT_KINDS:
            continue
        action = next(action for action in actions if action.get("id") == action_id)
        labels = set(action.get("labels", []))
        if not children_by_local_parent.get(action_id) and not labels & _BLOCKED_LABELS:
            errors.append(f"parent action {action_id!r} needs a child or blocked state")
    for action in actions:
        if not isinstance(action, dict) or action.get("kind") != "edit" or "body" not in action:
            continue
        issue = action.get("issue")
        condition = preconditions.get(str(issue), {}) if isinstance(issue, int) else {}
        if not isinstance(condition, dict) or not condition.get("body_sha256"):
            errors.append(f"body edit for #{issue} requires a body_sha256 precondition")

    try:
        _topological_create_ids([action for action in actions if isinstance(action, dict)])
    except BacklogPlanError as exc:
        errors.append(str(exc))
    return errors


def render_issue_body(action: dict[str, Any], resolved: dict[str, int] | None = None) -> str:
    spec = action["spec"]
    parent = action.get("parent")
    if isinstance(parent, str) and resolved and parent in resolved:
        parent = resolved[parent]
    lines = [f"<!-- chirp-backlog-key:{action['idempotency_key']} -->"]
    if parent is not None:
        lines += ["", f"Parent: #{parent}" if isinstance(parent, int) else f"Parent: ${parent}"]
    sections = [
        ("Outcome", spec["outcome"]),
        ("Immediate next action", spec["immediate_action"]),
        ("Context", spec.get("context")),
        ("Scope", spec["scope"]),
        ("Boundaries / not in this issue", spec["boundaries"]),
        ("Required proof", spec["proof"]),
        ("Acceptance criteria", spec["acceptance"]),
        ("Collateral", spec["collateral"]),
        ("Blocked until / revisit trigger", spec.get("blocked_until")),
    ]
    for heading, value in sections:
        if value:
            lines += ["", f"## {heading}", "", str(value).strip()]
    body = "\n".join(lines).rstrip() + "\n"
    if len(body) > _MAX_BODY:
        raise BacklogPlanError(f"rendered body for {action['id']!r} exceeds {_MAX_BODY} characters")
    return body


def _run(command: list[str], *, timeout: int = 60) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise BacklogPlanError(f"command failed ({' '.join(command[:3])}): {detail}")
    return result.stdout


def _gh_json(args: list[str]) -> Any:
    return json.loads(_run(["gh", *args]) or "null")


def _current_repository() -> str:
    value = _gh_json(["repo", "view", "--json", "nameWithOwner"])
    return str(value["nameWithOwner"])


def _current_sha() -> str:
    return _run(["git", "rev-parse", "HEAD"]).strip()


def _fetch_all_issues(repository: str) -> list[dict[str, Any]]:
    value = _gh_json(
        [
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--limit",
            "1000",
            "--json",
            "number,title,body,labels,state,updatedAt,url",
        ]
    )
    if not isinstance(value, list):
        raise BacklogPlanError("gh issue list returned a non-list response")
    if len(value) == 1000:
        raise BacklogPlanError(
            "issue inventory reached 1000; refuse potentially truncated idempotency scan"
        )
    return value


def _label_set(issue: dict[str, Any]) -> set[str]:
    return {
        str(label.get("name", "")) if isinstance(label, dict) else str(label)
        for label in issue.get("labels", [])
    }


def _is_gf(issue: dict[str, Any]) -> bool:
    return "good first issue" in _label_set(issue) or str(issue.get("title", "")).startswith("[GF]")


def _issue_rest(repository: str, number: int) -> dict[str, Any]:
    value = _gh_json(["api", f"repos/{repository}/issues/{number}"])
    if not isinstance(value, dict):
        raise BacklogPlanError(f"GitHub returned no issue object for #{number}")
    return value


def _comments(repository: str, number: int) -> list[dict[str, Any]]:
    value = _gh_json(
        [
            "api",
            f"repos/{repository}/issues/{number}/comments?per_page=100",
            "--paginate",
            "--slurp",
        ]
    )
    pages = value if isinstance(value, list) else []
    if pages and all(isinstance(page, list) for page in pages):
        return [comment for page in pages for comment in page]
    return pages


def _relation_numbers(repository: str, number: int, relation: str) -> set[int]:
    value = _gh_json(
        [
            "api",
            f"repos/{repository}/issues/{number}/{relation}?per_page=100",
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
    return {int(item["number"]) for item in rows}


def _database_id(repository: str, number: int) -> int:
    return int(_issue_rest(repository, number)["id"])


def _write_journal(path: Path, journal: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _refresh_seen(repository: str, journal: dict[str, Any], numbers: set[int]) -> None:
    seen = journal.setdefault("last_seen", {})
    for number in numbers:
        seen[str(number)] = _issue_rest(repository, number)["updated_at"]


def _resolve(ref: int | str | None, resolved: dict[str, int]) -> int | None:
    if ref is None or isinstance(ref, int):
        return ref
    if ref not in resolved:
        raise BacklogPlanError(f"plan-local reference {ref!r} has not been created")
    return resolved[ref]


def _comment_once(repository: str, number: int, body: str, key: str) -> None:
    marker = f"<!-- chirp-backlog-comment-key:{key} -->"
    matches = [
        comment
        for comment in _comments(repository, number)
        if marker in str(comment.get("body", ""))
    ]
    if len(matches) > 1:
        raise BacklogPlanError(f"duplicate comment marker {key!r} on #{number}")
    if matches:
        return
    _run(
        ["gh", "issue", "comment", str(number), "--repo", repository, "--body", f"{marker}\n{body}"]
    )


def _preflight(
    plan: dict[str, Any],
    journal: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], dict[str, int]]:
    repository = plan["repository"]
    if repository != _current_repository():
        raise BacklogPlanError(
            f"plan repository {repository!r} does not match current repository {_current_repository()!r}"
        )
    if plan.get("baseline_sha") and plan["baseline_sha"] != _current_sha():
        raise BacklogPlanError("git HEAD changed since the backlog survey")
    issues = _fetch_all_issues(repository)
    by_number = {int(issue["number"]): issue for issue in issues}
    open_graph = {issue["number"]: issue for issue in fetch_open_issues(repository=repository)}
    parents = {
        number: int(issue["parent"]["number"])
        for number, issue in open_graph.items()
        if issue.get("parent")
    }

    def protected(number: int) -> bool:
        visited: set[int] = set()
        while number not in visited:
            visited.add(number)
            issue = by_number.get(number)
            if issue and _is_gf(issue):
                return True
            if number not in parents:
                return False
            number = parents[number]
        return True

    touched: set[int] = set()
    for action in plan["actions"]:
        if action["kind"] != "create":
            touched.add(action["issue"])
        for value in [action.get("parent"), *action.get("blocked_by", [])]:
            if isinstance(value, int):
                touched.add(value)
    for number in sorted(touched):
        if number not in by_number:
            raise BacklogPlanError(f"touched issue #{number} does not exist")
        if protected(number):
            raise BacklogPlanError(f"refusing to mutate good-first issue or subtree #{number}")
        expected = journal.get("last_seen", {}).get(str(number))
        condition = plan.get("preconditions", {}).get(str(number), {})
        expected = expected or condition.get("updated_at")
        if not expected:
            raise BacklogPlanError(f"touched issue #{number} lacks an updated_at precondition")
        if by_number[number]["updatedAt"] != expected:
            raise BacklogPlanError(f"issue #{number} changed since the survey")
        body_hash = condition.get("body_sha256")
        if body_hash and _body_hash(by_number[number].get("body") or "") != body_hash:
            raise BacklogPlanError(f"issue #{number} body changed since the survey")

    marker_map: dict[str, list[int]] = {}
    for issue in issues:
        for key in _MARKER.findall(issue.get("body") or ""):
            marker_map.setdefault(key, []).append(int(issue["number"]))
    resolved: dict[str, int] = {
        action_id: int(value["issue"])
        for action_id, value in journal.get("actions", {}).items()
        if isinstance(value, dict) and value.get("issue")
    }
    adopted: dict[str, tuple[int, str]] = {}
    for action in plan["actions"]:
        if action["kind"] != "create":
            continue
        key = action["idempotency_key"]
        matches = marker_map.get(key, [])
        if len(matches) > 1:
            raise BacklogPlanError(f"idempotency marker {key!r} appears on multiple issues")
        if matches:
            resolved[action["id"]] = matches[0]
            adopted[action["id"]] = (matches[0], key)
    for action_id in _topological_create_ids(plan["actions"]):
        if action_id not in adopted:
            continue
        action = next(action for action in plan["actions"] if action["id"] == action_id)
        number, key = adopted[action_id]
        expected_body = render_issue_body(action, resolved)
        existing = by_number[number]
        if _body_hash(existing.get("body") or "") != _body_hash(expected_body):
            raise BacklogPlanError(
                f"idempotency marker {key!r} exists on #{number} with different content"
            )
    labels = _gh_json(["label", "list", "--repo", repository, "--limit", "1000", "--json", "name"])
    existing_labels = {item["name"] for item in labels}
    requested = {
        label
        for action in plan["actions"]
        for label in [
            *action.get("labels", []),
            *action.get("add_labels", []),
            *action.get("remove_labels", []),
        ]
    }
    missing_labels = sorted(requested - existing_labels)
    if missing_labels:
        raise BacklogPlanError(f"plan references missing labels: {', '.join(missing_labels)}")
    for action in plan["actions"]:
        if action["kind"] != "edit" or "ready" not in action.get("add_labels", []):
            continue
        number = action["issue"]
        current = open_graph.get(number)
        if current is None:
            raise BacklogPlanError(f"cannot promote closed or missing issue #{number} to ready")
        current_labels = set(current.get("labels", []))
        if current.get("subIssues") or current_labels & {"saga", "epic", "implementation-epic"}:
            raise BacklogPlanError(f"ready is leaf-only; #{number} is a parent")
        removed = set(action.get("remove_labels", []))
        if (current_labels & _BLOCKED_LABELS) - removed:
            raise BacklogPlanError(f"#{number} still carries a blocked label")
        open_blockers = {
            blocker
            for blocker in _relation_numbers(repository, number, "dependencies/blocked_by")
            if str(by_number.get(blocker, {}).get("state", "OPEN")).upper() == "OPEN"
        }
        if open_blockers:
            joined = ", ".join(f"#{blocker}" for blocker in sorted(open_blockers))
            raise BacklogPlanError(f"#{number} still has open formal blockers: {joined}")
    return issues, by_number, resolved


def apply_plan(
    plan: dict[str, Any], plan_path: str, *, apply: bool, resume: bool, allow_close: bool
) -> str:
    errors = validate_plan(plan)
    if errors:
        raise BacklogPlanError("invalid backlog plan:\n- " + "\n- ".join(errors))
    journal_path = (
        Path(f"{plan_path}.journal.json")
        if plan_path != "-"
        else Path(".backlog-plan.journal.json")
    )
    plan_hash = _json_hash(plan)
    if journal_path.exists():
        if not resume:
            raise BacklogPlanError(f"journal exists; rerun with --resume: {journal_path}")
        journal = cast(dict[str, Any], json.loads(journal_path.read_text(encoding="utf-8")))
        if journal.get("plan_sha256") != plan_hash:
            raise BacklogPlanError("journal belongs to a different plan")
    else:
        journal = {"plan_sha256": plan_hash, "actions": {}, "phases": {}, "last_seen": {}}
    _, _, resolved = _preflight(plan, journal)
    actions = {action["id"]: action for action in plan["actions"]}
    create_order = _topological_create_ids(plan["actions"])
    lines = [f"# Backlog plan {'apply' if apply else 'dry run'}", ""]
    for action_id in create_order:
        action = actions[action_id]
        if action["kind"] != "create":
            continue
        if action_id in resolved:
            lines.append(f"- adopt #{resolved[action_id]} for `{action_id}`")
        else:
            lines.append(f"- create `{action_id}`: {action['title']}")
    lines.extend(
        f"- {action['kind']} #{action['issue']} via `{action['id']}`"
        for action in plan["actions"]
        if action["kind"] != "create"
    )
    if not apply:
        return "\n".join(lines) + "\n"

    repository = plan["repository"]
    close_actions = [action for action in plan["actions"] if action["kind"] == "close"]
    if close_actions and not allow_close:
        raise BacklogPlanError("plan contains close actions; rerun with --allow-close")

    def record(phase: str, action_id: str, numbers: set[int] | None = None) -> None:
        phases = cast(dict[str, list[str]], journal.setdefault("phases", {}))
        phases.setdefault(phase, []).append(action_id)
        if numbers:
            _refresh_seen(repository, journal, set(numbers))
        _write_journal(journal_path, journal)

    for action_id in create_order:
        action = actions[action_id]
        if action["kind"] != "create" or action_id in resolved:
            continue
        body = render_issue_body(action, resolved)
        labels = [label for label in action["labels"] if label != "ready"]
        command = [
            "gh",
            "issue",
            "create",
            "--repo",
            repository,
            "--title",
            action["title"],
            "--body",
            body,
        ]
        for label in labels:
            command += ["--label", label]
        url = _run(command).strip().splitlines()[-1]
        number = int(url.rstrip("/").rsplit("/", 1)[-1])
        resolved[action_id] = number
        journal_actions = cast(dict[str, dict[str, int]], journal.setdefault("actions", {}))
        journal_actions[action_id] = {"issue": number}
        record("create", action_id, {number})

    graph = {issue["number"]: issue for issue in fetch_open_issues(repository=repository)}
    for action in plan["actions"]:
        parent = _resolve(action.get("parent"), resolved)
        if parent is None:
            continue
        child = resolved[action["id"]] if action["kind"] == "create" else action["issue"]
        current_parent = graph.get(child, {}).get("parent")
        if current_parent and int(current_parent["number"]) != parent:
            raise BacklogPlanError(
                f"#{child} already belongs to parent #{current_parent['number']}; reparenting is not allowed"
            )
        if not current_parent:
            _run(
                [
                    "gh",
                    "api",
                    "--method",
                    "POST",
                    f"repos/{repository}/issues/{parent}/sub_issues",
                    "-F",
                    f"sub_issue_id={_database_id(repository, child)}",
                ]
            )
        record("parent", action["id"], {parent, child})

    for action in plan["actions"]:
        blocked_issue = (
            resolved[action["id"]] if action["kind"] == "create" else action.get("issue")
        )
        if blocked_issue is None:
            continue
        existing = _relation_numbers(repository, blocked_issue, "dependencies/blocked_by")
        for ref in action.get("blocked_by", []):
            blocker = _resolve(ref, resolved)
            if blocker is None:
                raise BacklogPlanError(f"action {action['id']!r} has an empty blocker reference")
            if blocker not in existing:
                _run(
                    [
                        "gh",
                        "api",
                        "--method",
                        "POST",
                        f"repos/{repository}/issues/{blocked_issue}/dependencies/blocked_by",
                        "-F",
                        f"issue_id={_database_id(repository, blocker)}",
                    ]
                )
        if action.get("blocked_by"):
            blocker_numbers = {
                blocker
                for ref in action["blocked_by"]
                if (blocker := _resolve(ref, resolved)) is not None
            }
            record(
                "blocker",
                action["id"],
                {blocked_issue, *blocker_numbers},
            )

    for action in plan["actions"]:
        if action["kind"] != "edit":
            continue
        command = ["gh", "issue", "edit", str(action["issue"]), "--repo", repository]
        changed = False
        if "title" in action:
            command += ["--title", action["title"]]
            changed = True
        if "body" in action:
            command += ["--body", action["body"]]
            changed = True
        if changed:
            _run(command)
            record("content", action["id"], {action["issue"]})

    for action in plan["actions"]:
        if action.get("comment"):
            issue = resolved[action["id"]] if action["kind"] == "create" else action["issue"]
            _comment_once(repository, issue, action["comment"], action["comment_key"])
            record("comment", action["id"], {issue})

    for action in plan["actions"]:
        issue = resolved[action["id"]] if action["kind"] == "create" else action.get("issue")
        if issue is None or action["kind"] in {"comment", "close"}:
            continue
        add = list(action["labels"] if action["kind"] == "create" else action.get("add_labels", []))
        remove = list(action.get("remove_labels", []))
        if not add and not remove:
            continue
        command = ["gh", "issue", "edit", str(issue), "--repo", repository]
        for label in sorted(set(add), key=lambda value: (value == "ready", value)):
            command += ["--add-label", label]
        for label in remove:
            command += ["--remove-label", label]
        _run(command)
        record("labels", action["id"], {issue})

    for action in close_actions:
        if action.get("comment"):
            _comment_once(repository, action["issue"], action["comment"], action["comment_key"])
        _run(
            [
                "gh",
                "issue",
                "close",
                str(action["issue"]),
                "--repo",
                repository,
                "--reason",
                "not planned" if action["reason"] == "not_planned" else "completed",
            ]
        )
        record("close", action["id"], {action["issue"]})

    verification = derive_workability_findings(
        fetch_open_issues(repository=repository, include_dependencies=True)
    )
    lines += [
        "",
        f"Applied {len(plan['actions'])} action(s).",
        f"Workability findings after apply: {len(verification)}",
    ]
    return "\n".join(lines) + "\n"


def _labels(issue: dict[str, Any]) -> set[str]:
    return {label_name(label) for label in issue.get("labels", [])}


def _priority_values(labels: set[str]) -> tuple[str, ...]:
    priorities: set[str] = set()
    for label in labels:
        normalized = label.strip().lower().replace(" ", "")
        match = re.fullmatch(r"(?:priority[:/])?(p[0-3])", normalized)
        if match:
            priorities.add(match.group(1).upper())
    return tuple(sorted(priorities, key=_PRIORITY_ORDER.__getitem__))


def _priority(labels: set[str]) -> str:
    values = _priority_values(labels)
    return values[0] if values else "unprioritized"


def _issue_kind(issue: dict[str, Any]) -> str:
    labels = {label.lower() for label in _labels(issue)}
    for kind in ("saga", "epic", "rfc", "bug", "task"):
        if kind in labels or f"type:{kind}" in labels or f"type/{kind}" in labels:
            return kind
    return "epic" if issue.get("subIssues") else "task"


def _body_section(body: str, heading: str) -> str:
    match = re.search(
        rf"(?ims)^#{{2,3}}\s+{re.escape(heading)}\s*$\n(.*?)(?=^#{{2,3}}\s+|\Z)", body
    )
    return match.group(1).strip() if match else ""


def _first_action_paragraph(body: str) -> str:
    without_comments = re.sub(r"(?s)<!--.*?-->", "", body)
    if re.search(r"(?m)^#{2,3}\s+", without_comments):
        return ""
    for paragraph in re.split(r"\n\s*\n", without_comments):
        value = paragraph.strip()
        if not value or value.startswith("#"):
            continue
        if re.match(r"(?i)^parent\s*:", value) or re.match(r"^#\d+\s*[;.]", value):
            continue
        return value
    return ""


def _execution_context(body: str) -> tuple[str, str, str, list[str]]:
    warnings: list[str] = []
    immediate_action = _body_section(body, "Immediate next action")
    if not immediate_action:
        for heading in ("Decision to record", "Outcome", "Scope", "Required decisions"):
            immediate_action = _body_section(body, heading)
            if immediate_action:
                warnings.append(f"immediate action derived from legacy {heading!r} section")
                break
    if not immediate_action:
        immediate_action = _first_action_paragraph(body)
        if immediate_action:
            warnings.append("immediate action inferred from the first actionable body paragraph")

    required_proof = _body_section(body, "Required proof") or _body_section(
        body, "Required proof plan"
    )
    acceptance = _body_section(body, "Acceptance criteria") or _body_section(body, "Exit")
    if not required_proof and acceptance:
        required_proof = acceptance
        warnings.append("required proof derived from acceptance/exit criteria")
    return immediate_action, required_proof, acceptance, warnings


def _area_tokens(issue: dict[str, Any]) -> set[str]:
    areas: set[str] = set()
    for label in _labels(issue):
        normalized = label.strip().lower()
        if not normalized:
            continue
        if normalized in _KNOWN_AREAS or (
            normalized not in _CONTROL_LABELS
            and not re.fullmatch(r"p[0-3]", normalized)
            and not normalized.startswith(
                (
                    "area:",
                    "area/",
                    "component:",
                    "component/",
                    "priority:",
                    "priority/",
                    "type:",
                    "type/",
                )
            )
        ):
            areas.add(normalized.replace(" ", "-"))
        for prefix in ("area:", "area/", "component:", "component/"):
            if normalized.startswith(prefix):
                value = normalized.removeprefix(prefix).strip().replace(" ", "-")
                if value:
                    areas.add(value)
    body = str(issue.get("body") or "").lower()
    areas |= set(re.findall(r"(?:src/chirp|tests)/([a-z0-9_-]+)(?:/|\b)", body))
    return areas


def _parent_context(
    issue: dict[str, Any], by_number: dict[int, dict[str, Any]]
) -> tuple[list[int], list[dict[str, Any]], list[str]]:
    chain: list[int] = []
    ancestors: list[dict[str, Any]] = []
    problems: list[str] = []
    current = issue
    seen = {int(issue["number"])}
    while current.get("parent"):
        parent = current["parent"]
        number = int(parent["number"] if isinstance(parent, dict) else parent)
        chain.append(number)
        if number in seen:
            problems.append(f"native parent cycle reaches #{number}")
            break
        seen.add(number)
        ancestor = by_number.get(number)
        if ancestor is None:
            problems.append(f"parent #{number} is not open")
            break
        ancestors.append(ancestor)
        labels = _labels(ancestor)
        if _is_gf(ancestor):
            problems.append(f"parent #{number} is reserved for contributors")
        if labels & _BLOCKED_LABELS:
            problems.append(f"parent #{number} is blocked")
        if "ready" in labels:
            problems.append(f"parent #{number} incorrectly carries ready")
        current = ancestor
    return chain, ancestors, problems


def assess_work(issues: list[dict], open_prs: list[dict]) -> list[WorkAssessment]:
    """Purely assess every issue against the immediate-work eligibility gates."""
    by_number = {int(issue["number"]): issue for issue in issues}
    claims: dict[int, list[dict]] = {}
    for pr in open_prs:
        for number in pr_work_claims(pr):
            claims.setdefault(number, []).append(pr)

    unlocks: dict[int, set[int]] = {}
    for issue in issues:
        if str(issue.get("state", "OPEN")).upper() != "OPEN":
            continue
        for blocker in issue.get("blockedBy", []):
            if str(blocker.get("state", "OPEN")).upper() == "OPEN":
                unlocks.setdefault(int(blocker["number"]), set()).add(int(issue["number"]))

    assessments: list[WorkAssessment] = []
    for issue in issues:
        number = int(issue["number"])
        labels = _labels(issue)
        kind = _issue_kind(issue)
        chain, ancestors, parent_problems = _parent_context(issue, by_number)
        open_blockers = tuple(
            sorted(
                int(blocker["number"])
                for blocker in issue.get("blockedBy", [])
                if str(blocker.get("state", "OPEN")).upper() == "OPEN"
            )
        )
        claimed = tuple(
            sorted(
                (
                    int(pr["number"]),
                    str(pr.get("url") or ""),
                    bool(pr.get("isDraft", False)),
                )
                for pr in claims.get(number, [])
            )
        )
        body = str(issue.get("body") or "")
        immediate_action, required_proof, acceptance, context_warnings = _execution_context(body)
        is_open = str(issue.get("state", "OPEN")).upper() == "OPEN"
        contributor_owned = not _is_gf(issue) and not any(_is_gf(item) for item in ancestors)
        is_parent = bool(labels & _PARENT_LABELS) or bool(issue.get("subIssues"))
        checks = (
            ("open", is_open, "issue is open" if is_open else "issue is not open"),
            (
                "maintainer-owned",
                contributor_owned,
                "not reserved as good-first work"
                if contributor_owned
                else "issue or ancestor is reserved for contributors",
            ),
            (
                "leaf",
                not is_parent,
                "issue is an executable leaf" if not is_parent else "parent issues are not picked",
            ),
            (
                "ready",
                "ready" in labels,
                "ready is explicit" if "ready" in labels else "ready label is missing",
            ),
            (
                "work-state",
                not bool(labels & _BLOCKED_LABELS),
                "no blocked label remains"
                if not labels & _BLOCKED_LABELS
                else "blocked label remains",
            ),
            (
                "formal-blockers",
                not open_blockers,
                "no open formal blockers"
                if not open_blockers
                else "open blocker(s): " + ", ".join(f"#{item}" for item in open_blockers),
            ),
            (
                "parent-chain",
                not parent_problems,
                (
                    "healthy " + " → ".join(f"#{item}" for item in chain)
                    if chain and not parent_problems
                    else "; ".join(parent_problems) or "standalone leaf"
                ),
            ),
            (
                "unclaimed",
                not claimed,
                "no open PR claims this issue"
                if not claimed
                else "open PR(s): " + ", ".join(f"#{item[0]}" for item in claimed),
            ),
            (
                "decision-clear",
                kind == "rfc" or not bool(labels & _DECISION_GATE_LABELS),
                "decision work is executable now"
                if kind == "rfc"
                else (
                    "no unresolved decision label"
                    if not labels & _DECISION_GATE_LABELS
                    else "an unresolved decision label remains"
                ),
            ),
            (
                "immediate-action",
                bool(immediate_action),
                "immediate next action is documented"
                if immediate_action
                else "body has no Immediate next action section",
            ),
        )
        failures = tuple(detail for _name, passed, detail in checks if not passed)
        priority_values = _priority_values(labels)
        issue_priority = priority_values[0] if priority_values else "unprioritized"
        inherited_priorities = [
            value for ancestor in ancestors for value in _priority_values(_labels(ancestor))
        ]
        effective_priority = min(
            [issue_priority, *inherited_priorities], key=_PRIORITY_ORDER.__getitem__
        )
        warnings: list[str] = []
        warnings.extend(context_warnings)
        if not priority_values:
            warnings.append("no priority label; ranked after P3")
        elif len(priority_values) > 1:
            warnings.append("multiple priority labels; highest urgency wins")
        if not required_proof:
            warnings.append("required proof is not documented")
        if not acceptance:
            warnings.append("acceptance criteria are not documented")
        issue_areas = _area_tokens(issue)
        for ancestor in ancestors:
            issue_areas |= _area_tokens(ancestor)
        direct_unlocks = tuple(sorted(unlocks.get(number, set())))
        reasons = failures
        if not failures:
            positive = ["explicitly ready, unblocked, and unclaimed"]
            if chain:
                positive.append("native parent chain is healthy")
            if direct_unlocks:
                positive.append(
                    "completion directly unlocks "
                    + ", ".join(f"#{item}" for item in direct_unlocks)
                )
            reasons = tuple(positive)
        assessments.append(
            WorkAssessment(
                number=number,
                title=str(issue.get("title") or ""),
                url=str(issue.get("url") or ""),
                kind=kind,
                labels=tuple(sorted(labels)),
                eligible=not failures,
                checks=checks,
                reasons=reasons,
                warnings=tuple(warnings),
                priority=issue_priority,
                effective_priority=effective_priority,
                parent_chain=tuple(chain),
                blocked_by=open_blockers,
                open_prs=claimed,
                unlocks=direct_unlocks,
                areas=tuple(sorted(issue_areas)),
                created_at=str(issue.get("createdAt") or issue.get("created_at") or ""),
                immediate_action=immediate_action,
                required_proof=required_proof,
                acceptance=acceptance,
            )
        )
    return assessments


def rank_work(
    assessments: list[WorkAssessment],
    *,
    area: str | None = None,
    kind: str | None = None,
    limit: int = 5,
) -> list[WorkAssessment]:
    """Filter eligible assessments and rank them with a transparent policy."""
    normalized_area = area.strip().lower().replace(" ", "-") if area else None
    candidates = [
        item
        for item in assessments
        if item.eligible
        and (normalized_area is None or normalized_area in item.areas)
        and (kind is None or item.kind == kind)
    ]
    candidates.sort(
        key=lambda item: (
            _PRIORITY_ORDER[item.effective_priority],
            -len(item.unlocks),
            item.created_at or "9999-12-31T23:59:59Z",
            item.number,
        )
    )
    return candidates[:limit]


def _markdown_continuation(value: str) -> str:
    return value.replace("\n", "\n     ")


def render_next(candidates: list[WorkAssessment]) -> str:
    lines = ["# Next workable issues", ""]
    if not candidates:
        return "\n".join(
            [
                *lines,
                "_No issue passes every eligibility gate and requested filter._",
                "Run `backlog.py doctor --strict` and `backlog.py explain <issue>` to find why.",
                "",
            ]
        )
    for index, item in enumerate(candidates, 1):
        target = f"[#{item.number}]({item.url})" if item.url else f"#{item.number}"
        lines.append(f"{index}. {target} {item.title}")
        lines.append(
            f"   - Rank: {item.effective_priority}; directly unlocks {len(item.unlocks)} issue(s)"
        )
        lines.append(f"   - Why now: {'; '.join(item.reasons)}")
        if item.parent_chain:
            lines.append(
                "   - Parent chain: " + " → ".join(f"#{number}" for number in item.parent_chain)
            )
        if item.areas:
            lines.append(f"   - Areas: {', '.join(item.areas)}")
        lines.append(f"   - Immediate action: {_markdown_continuation(item.immediate_action)}")
        lines.append(
            "   - Required proof: "
            + _markdown_continuation(item.required_proof or "not documented; groom before closure")
        )
        if item.warnings:
            lines.append(f"   - Warnings: {'; '.join(item.warnings)}")
        lines.append("")
    return "\n".join(lines)


def render_explain(assessment: WorkAssessment) -> str:
    target = (
        f"[#{assessment.number}]({assessment.url})" if assessment.url else f"#{assessment.number}"
    )
    lines = [
        f"# Workability explanation: {target} {assessment.title}",
        "",
        f"**Status:** {'workable now' if assessment.eligible else 'not currently workable'}",
        f"**Kind:** {assessment.kind}",
        f"**Priority:** {assessment.priority} (effective: {assessment.effective_priority})",
        f"**Directly unlocks:** {', '.join(f'#{item}' for item in assessment.unlocks) or 'none'}",
        "",
        "## Eligibility checks",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} `{name}` — {detail}"
        for name, passed, detail in assessment.checks
    )
    lines += ["", "## Execution context", ""]
    lines.append(
        f"- Immediate action: {_markdown_continuation(assessment.immediate_action or 'not documented')}"
    )
    lines.append(
        f"- Required proof: {_markdown_continuation(assessment.required_proof or 'not documented')}"
    )
    lines.append(
        f"- Acceptance: {_markdown_continuation(assessment.acceptance or 'not documented')}"
    )
    lines.append(
        "- Parent chain: "
        + (" → ".join(f"#{item}" for item in assessment.parent_chain) or "standalone")
    )
    lines.append(f"- Areas: {', '.join(assessment.areas) or 'not identified'}")
    if assessment.warnings:
        lines += ["", "## Warnings", ""]
        lines.extend(f"- {warning}" for warning in assessment.warnings)
    lines.append("")
    return "\n".join(lines)


def _fetch_open_prs(repository: str) -> list[dict[str, Any]]:
    value = _gh_json(
        [
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--limit",
            "1000",
            "--json",
            "number,title,body,headRefName,url,isDraft",
        ]
    )
    if not isinstance(value, list):
        raise BacklogPlanError("gh pr list returned a non-list response")
    if len(value) == 1000:
        raise BacklogPlanError("open PR inventory reached 1000; refuse potentially truncated scan")
    return cast(list[dict[str, Any]], value)


def _closed_assessment(issue: dict[str, Any]) -> WorkAssessment:
    labels = _labels(issue)
    body = str(issue.get("body") or "")
    immediate_action, required_proof, acceptance, context_warnings = _execution_context(body)
    reason = str(issue.get("state_reason") or issue.get("stateReason") or "closed").lower()
    return WorkAssessment(
        number=int(issue["number"]),
        title=str(issue.get("title") or ""),
        url=str(issue.get("html_url") or issue.get("url") or ""),
        kind=_issue_kind(issue),
        labels=tuple(sorted(labels)),
        eligible=False,
        checks=(("open", False, f"issue is closed ({reason})"),),
        reasons=(f"issue is closed ({reason})",),
        warnings=tuple(context_warnings),
        priority=_priority(labels),
        effective_priority=_priority(labels),
        parent_chain=(),
        blocked_by=(),
        open_prs=(),
        unlocks=(),
        areas=tuple(sorted(_area_tokens(issue))),
        created_at=str(issue.get("created_at") or ""),
        immediate_action=immediate_action,
        required_proof=required_proof,
        acceptance=acceptance,
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _load_work_assessments(repository: str) -> list[WorkAssessment]:
    issues = fetch_open_issues(repository=repository, include_dependencies=True)
    if len(issues) == 1000:
        raise BacklogPlanError(
            "open issue inventory reached 1000; refuse potentially truncated ranking"
        )
    return assess_work(issues, _fetch_open_prs(repository))


def _find_assessment(
    repository: str, assessments: list[WorkAssessment], number: int
) -> WorkAssessment:
    assessment = next((item for item in assessments if item.number == number), None)
    if assessment is not None:
        return assessment
    remote = _issue_rest(repository, number)
    if str(remote.get("state", "")).upper() != "CLOSED":
        raise BacklogPlanError(f"open issue #{number} was absent from the authoritative inventory")
    return _closed_assessment(remote)


def _audit(repository: str | None, *, json_output: bool, strict: bool) -> int:
    issues = fetch_open_issues(repository=repository, include_dependencies=True)
    findings = derive_findings(issues, fetch_merged_prs(1000), collect_issue_tests())
    workability = derive_workability_findings(issues)
    if json_output:
        print(
            json.dumps(
                {"issues": issues, "reconciliation": findings, "workability": workability}, indent=2
            )
        )
    else:
        print(render_report(findings, collect_issue_tests()))
        print("\n# Backlog workability\n")
        if not workability:
            print("_No non-GF workability violations._")
        for finding in workability:
            print(f"- #{finding['number']} {finding['title']}: {'; '.join(finding['reasons'])}")
    violations = [
        finding
        for finding in workability
        if set(finding["codes"])
        & {
            "ready-parent",
            "parent-no-children",
            "parent-no-workable-leaf",
            "work-state-missing",
            "work-state-conflict",
            "blocked-without-dependency",
        }
    ]
    return 1 if strict and violations else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="read-only reconciliation and workability survey")
    audit.add_argument("--repo")
    audit.add_argument("--json", action="store_true")
    doctor = sub.add_parser("doctor", help="check the workable-backlog invariants")
    doctor.add_argument("--repo")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--strict", action="store_true")
    next_parser = sub.add_parser("next", help="rank immediately workable issues")
    next_parser.add_argument("--repo")
    next_parser.add_argument("--limit", type=_positive_int, default=5)
    next_parser.add_argument("--area")
    next_parser.add_argument("--kind", choices=sorted(_LEAF_KINDS))
    next_parser.add_argument("--json", action="store_true")
    explain = sub.add_parser("explain", help="explain why an issue is or is not workable")
    explain.add_argument("issue", type=_positive_int)
    explain.add_argument("--repo")
    explain.add_argument("--json", action="store_true")
    validate = sub.add_parser("validate", help="validate an ephemeral JSON plan")
    validate.add_argument("plan")
    apply_parser = sub.add_parser("apply", help="preflight and optionally apply a JSON plan")
    apply_parser.add_argument("plan")
    apply_parser.add_argument("--apply", action="store_true")
    apply_parser.add_argument("--resume", action="store_true")
    apply_parser.add_argument("--allow-close", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in {"audit", "doctor"}:
            return _audit(
                args.repo,
                json_output=args.json,
                strict=args.command == "doctor" and args.strict,
            )
        if args.command in {"next", "explain"}:
            repository = args.repo or _current_repository()
            assessments = _load_work_assessments(repository)
            if args.command == "next":
                candidates = rank_work(
                    assessments,
                    area=args.area,
                    kind=args.kind,
                    limit=args.limit,
                )
                if args.json:
                    print(
                        json.dumps(
                            {
                                "repository": repository,
                                "policy": [
                                    "eligible only",
                                    "effective priority",
                                    "direct unlock count",
                                    "oldest created",
                                    "issue number",
                                ],
                                "candidates": [item.as_json() for item in candidates],
                            },
                            indent=2,
                        )
                    )
                else:
                    print(render_next(candidates), end="")
                return 0
            assessment = _find_assessment(repository, assessments, args.issue)
            if args.json:
                print(
                    json.dumps(
                        {"repository": repository, "assessment": assessment.as_json()}, indent=2
                    )
                )
            else:
                print(render_explain(assessment), end="")
            return 0
        plan = load_plan(args.plan)
        if args.command == "validate":
            errors = validate_plan(plan)
            if errors:
                print("Invalid backlog plan:\n- " + "\n- ".join(errors))
                return 1
            print("Backlog plan is valid.")
            return 0
        print(
            apply_plan(
                plan,
                args.plan,
                apply=args.apply,
                resume=args.resume,
                allow_close=args.allow_close,
            ),
            end="",
        )
        return 0
    except (BacklogPlanError, json.JSONDecodeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"backlog: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
