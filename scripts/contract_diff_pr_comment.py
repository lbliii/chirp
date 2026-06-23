"""Post or update a PR comment with ``chirp diff`` hypermedia surface changes.

Issue #344 — advisory PR feedback until merge-blocking policy is signed off.
Stdlib-only GitHub I/O (``urllib``); diff logic lives in ``chirp.contracts``.

Usage (CI)::

    GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo PR_NUMBER=42 \\
        python scripts/contract_diff_pr_comment.py \\
        --app examples.chirpui.forum_shell.app:app \\
        --base origin/main
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from chirp.cli._diff import check_at_git_ref, collect_check_json, find_git_root  # noqa: E402
from chirp.cli._resolve import resolve_app  # noqa: E402
from chirp.contracts.diff import ContractDiff, diff_contract_dicts  # noqa: E402

_MARKER = "<!-- chirp-contract-diff -->"


def collect_diff_payload(
    app: str,
    base_ref: str,
    *,
    deploy: bool = False,
    include_info: bool = False,
) -> tuple[ContractDiff, dict]:
    """Run contract checks at *base_ref* and HEAD; return diff + JSON payload."""
    os.environ.setdefault("CHIRP_SKIP_CONTRACT_CHECKS", "1")
    repo_root = find_git_root()
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    resolved = resolve_app(app)
    _, current = collect_check_json(
        resolved,
        deploy=deploy,
        include_info=include_info,
    )
    baseline = check_at_git_ref(
        app,
        base_ref,
        repo_root=repo_root,
        deploy=deploy,
        include_info=include_info,
    )
    diff = diff_contract_dicts(baseline, current)
    payload = {
        "base_ref": base_ref,
        "app": app,
        "baseline": baseline,
        "current": current,
        "diff": {"added": list(diff.added), "removed": list(diff.removed)},
    }
    return diff, payload


def _github_request(
    method: str,
    url: str,
    token: str,
    *,
    data: dict | None = None,
) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def upsert_pr_comment(
    *,
    repository: str,
    pr_number: int,
    body: str,
    token: str,
) -> None:
    """Create or update the bot comment identified by ``_MARKER``."""
    owner, repo = repository.split("/", 1)
    base = f"https://api.github.com/repos/{owner}/{repo}"
    comments_url = f"{base}/issues/{pr_number}/comments"
    try:
        existing = _github_request("GET", comments_url, token)
    except urllib.error.HTTPError as exc:
        msg = f"Could not list PR comments: {exc.reason}"
        raise SystemExit(msg) from exc

    for comment in existing:
        if _MARKER in (comment.get("body") or ""):
            comment_id = comment["id"]
            patch_url = f"{base}/issues/comments/{comment_id}"
            _github_request("PATCH", patch_url, token, data={"body": body})
            return

    _github_request("POST", comments_url, token, data={"body": body})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post chirp diff summary to a PR")
    parser.add_argument("--app", required=True, help="App import string")
    parser.add_argument("--base", required=True, help="Git base ref (e.g. origin/main)")
    parser.add_argument("--deploy", action="store_true", help="Production-posture severity")
    parser.add_argument(
        "--include-info",
        action="store_true",
        help="Include INFO-severity issues",
    )
    parser.add_argument(
        "--fail-on-new-errors",
        action="store_true",
        help="Exit 1 when the diff introduces contract errors",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print comment body instead of posting to GitHub",
    )
    args = parser.parse_args(argv)

    diff, payload = collect_diff_payload(
        args.app,
        args.base,
        deploy=args.deploy,
        include_info=args.include_info,
    )
    comment = diff.markdown_comment(app=args.app, base_ref=args.base)

    if args.dry_run:
        print(comment)
        print(json.dumps(payload, indent=2))
    else:
        token = os.environ.get("GITHUB_TOKEN")
        repository = os.environ.get("GITHUB_REPOSITORY")
        pr_number = os.environ.get("PR_NUMBER")
        if not token or not repository or not pr_number:
            msg = "GITHUB_TOKEN, GITHUB_REPOSITORY, and PR_NUMBER are required"
            raise SystemExit(msg)
        upsert_pr_comment(
            repository=repository,
            pr_number=int(pr_number),
            body=comment,
            token=token,
        )

    if args.fail_on_new_errors and diff.added_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
