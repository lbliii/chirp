"""Map ``@pytest.mark.issue(N)`` markers to the tests that carry them.

This is the offline half of the backlog-truth machinery (see
``docs/backlog-automation.md``). It answers a single question that the issue
tracker cannot: *which GitHub issues have an executable acceptance test, and
which do not?* "Done" then stops being a checkbox a human ticks and becomes a
fact a machine derives — a test either proves the acceptance criterion or it
does not exist.

Design constraints (mirrors ``scripts/check_roadmap_staleness.py``):

- **Stdlib only, no network, returns 0/1, prints an actionable message** so it
  runs anywhere (pre-commit, CI, an air-gapped laptop).
- **AST-based, not regex** — it understands function, class, and module-level
  (``pytestmark``) markers and ignores markers inside strings/comments.

Usage::

    python scripts/issue_coverage.py                 # table of issue -> tests
    python scripts/issue_coverage.py --issue 143      # tests proving #143
    python scripts/issue_coverage.py --json           # machine-readable map
    python scripts/issue_coverage.py --untested 143 146  # exit 1 if any lack tests
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_TEST_ROOTS = ("tests", "examples")


def _issue_args_from_decorator(node: ast.expr) -> list[int]:
    """Return the int issue numbers from a ``pytest.mark.issue(...)`` decorator.

    Accepts ``@pytest.mark.issue(143)``, ``@pytest.mark.issue(143, 185)`` and the
    ``mark.issue(...)`` / bare ``issue(...)`` import aliases. Non-int args are
    ignored (they would fail the marker contract, but this tool stays lenient).
    """
    if not isinstance(node, ast.Call):
        return []
    func = node.func
    # Match an attribute access ending in ``.issue`` (pytest.mark.issue / mark.issue).
    if not (isinstance(func, ast.Attribute) and func.attr == "issue"):
        return []
    return [
        arg.value
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, int)
    ]


def _module_level_issue_markers(tree: ast.Module) -> list[int]:
    """Issue numbers declared via a module-level ``pytestmark`` assignment."""
    issues: list[int] = []
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            continue
        value = node.value
        marks: Iterable[ast.expr]
        if isinstance(value, (ast.List, ast.Tuple)):
            marks = value.elts
        elif value is not None:
            marks = [value]
        else:
            marks = []
        for mark in marks:
            issues.extend(_issue_args_from_decorator(mark))
    return issues


def _qualname(stack: list[str], name: str) -> str:
    return "::".join([*stack, name])


def _collect_from_body(
    body: list[ast.stmt],
    stack: list[str],
    inherited: set[int],
    rel: str,
    record,
) -> None:
    """Record markers on functions/classes in *body*, propagating class markers down."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            own = {n for dec in node.decorator_list for n in _issue_args_from_decorator(dec)}
            for issue in own | inherited:
                record(issue, f"{rel}::{_qualname(stack, node.name)}")
        elif isinstance(node, ast.ClassDef):
            cls_issues = {n for dec in node.decorator_list for n in _issue_args_from_decorator(dec)}
            _collect_from_body(node.body, [*stack, node.name], inherited | cls_issues, rel, record)


def collect_issue_tests(
    roots: Iterable[Path] | None = None,
) -> dict[int, list[str]]:
    """Walk the test roots and return ``{issue_number: [test locations]}``.

    A location is ``relative/path.py::Class::test`` (or ``::module`` for a
    module-level ``pytestmark``). Class-level markers attribute every test in the
    class; function-level markers attribute that function.
    """
    if roots is None:
        roots = [_REPO_ROOT / r for r in _DEFAULT_TEST_ROOTS]
    mapping: dict[int, set[str]] = {}

    def _record(issue: int, location: str) -> None:
        mapping.setdefault(issue, set()).add(location)

    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("test_*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except OSError, SyntaxError:
                continue
            try:
                rel = path.relative_to(_REPO_ROOT).as_posix()
            except ValueError:
                # Fixture/test root outside the repo (unit tests pass a tmp dir).
                rel = path.name

            for issue in _module_level_issue_markers(tree):
                _record(issue, f"{rel}::<module>")

            _collect_from_body(tree.body, [], set(), rel, _record)

    return {issue: sorted(locs) for issue, locs in sorted(mapping.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", type=int, help="show tests proving a single issue")
    parser.add_argument("--json", action="store_true", help="emit the full map as JSON")
    parser.add_argument(
        "--untested",
        type=int,
        nargs="+",
        metavar="N",
        help="exit 1 if any listed issue has no acceptance test",
    )
    args = parser.parse_args(argv)

    coverage = collect_issue_tests()

    if args.untested is not None:
        missing = [n for n in args.untested if n not in coverage]
        if missing:
            print(
                "Issues without a @pytest.mark.issue acceptance test: "
                + ", ".join(f"#{n}" for n in missing)
            )
            return 1
        print("All listed issues have at least one acceptance test.")
        return 0

    if args.json:
        print(json.dumps(coverage, indent=2))
        return 0

    if args.issue is not None:
        locs = coverage.get(args.issue, [])
        if not locs:
            print(f"#{args.issue}: no acceptance test (@pytest.mark.issue({args.issue})) found.")
            return 0
        print(f"#{args.issue}: {len(locs)} acceptance test(s)")
        for loc in locs:
            print(f"  {loc}")
        return 0

    if not coverage:
        print("No @pytest.mark.issue(...) markers found yet. See docs/backlog-automation.md.")
        return 0
    print(f"{len(coverage)} issue(s) with acceptance tests:")
    for issue, locs in coverage.items():
        print(f"  #{issue}: {len(locs)} test(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
