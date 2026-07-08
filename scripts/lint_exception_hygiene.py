"""Ratchet exception hygiene without hiding Chirp's existing debt.

The gate scans production Python for three review-sensitive patterns:

1. Public-scope static raise messages with fewer than eight words or no final
   punctuation.
2. ``contextlib.suppress(...)`` without an inline ``# silent: <reason>``
   justification.
3. ``except`` handlers containing only ``pass`` / ``continue`` without the same
   explicit justification.
4. ``load_yaml(...) or {}``-style fallbacks that can mask a failed or empty
   configuration load.

Existing findings live in a semantic baseline so CI rejects new debt without a
cross-domain rewrite. Fingerprints exclude line numbers, so moving code does not
create churn. Removing or deliberately fixing a finding makes the baseline
stale and fails until ``--write-baseline`` is run in the same change.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

MIN_WORDS = 8
DEFAULT_SOURCE = Path("src/chirp")
DEFAULT_BASELINE = Path("scripts/exception_hygiene_baseline.json")


@dataclass(frozen=True, slots=True, order=True)
class Violation:
    """One stable exception-hygiene finding."""

    rule: str
    path: str
    scope: str
    evidence: str
    line: int

    @property
    def fingerprint(self) -> str:
        """Return a line-number-independent baseline identity."""
        return "|".join((self.rule, self.path, self.scope, self.evidence))

    def display(self) -> str:
        """Render an actionable diagnostic."""
        scope = f" ({self.scope})" if self.scope else ""
        return f"{self.path}:{self.line}: {self.rule}{scope}: {self.evidence}"


def _static_text(node: ast.AST) -> str | None:
    """Return the statically visible portion of a raise message."""
    match node:
        case ast.Constant(value=str() as value):
            return value
        case ast.JoinedStr(values=values):
            parts: list[str] = []
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    parts.append(" <value> ")
            return "".join(parts)
        case ast.BinOp(op=ast.Add()):
            left = _static_text(node.left)
            right = _static_text(node.right)
            if left is None and right is None:
                return None
            return (left or "") + (right or "")
        case _:
            return None


def _is_private_scope(scopes: list[str]) -> bool:
    """Return whether the innermost function is private but not a dunder."""
    for name in reversed(scopes):
        if name.startswith("__") and name.endswith("__"):
            return False
        return name.startswith("_")
    return False


def _scope_name(scopes: list[str]) -> str:
    return ".".join(scopes)


def _has_silent_reason(lines: list[str], lineno: int) -> bool:
    """Recognize an explicit, non-empty ``# silent:`` justification."""
    current = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    marker = "# silent:"
    if marker in current and current.partition(marker)[2].strip():
        return True
    previous = lines[lineno - 2] if lineno > 1 else ""
    return marker in previous and bool(previous.partition(marker)[2].strip())


def _raise_evidence(text: str) -> str | None:
    stripped = " ".join(text.split())
    problems: list[str] = []
    if not stripped:
        problems.append("empty message")
    else:
        if not stripped.endswith((".", "?")):
            problems.append("missing final punctuation")
        words = len(stripped.split())
        if words < MIN_WORDS:
            problems.append(f"{words} words (minimum {MIN_WORDS})")
    if not problems:
        return None
    return f"{'; '.join(problems)}; message={stripped!r}"


def _is_suppress(node: ast.Call) -> bool:
    func = node.func
    is_suppress = (isinstance(func, ast.Name) and func.id == "suppress") or (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "contextlib"
        and func.attr == "suppress"
    )
    return is_suppress


def _masked_load_name(node: ast.BoolOp) -> str | None:
    """Return the loader hidden by an ``or {}`` fallback, when statically visible."""
    if not isinstance(node.op, ast.Or) or not node.values:
        return None
    fallback = node.values[-1]
    if not isinstance(fallback, ast.Dict) or fallback.keys:
        return None
    candidate = node.values[-2] if len(node.values) >= 2 else None
    if isinstance(candidate, ast.Await):
        candidate = candidate.value
    if not isinstance(candidate, ast.Call):
        return None
    func = candidate.func
    name = (
        func.id
        if isinstance(func, ast.Name)
        else func.attr
        if isinstance(func, ast.Attribute)
        else ""
    )
    return name if name in {"load_yaml", "load_json", "load_toml", "load_config"} else None


def scan_file(path: Path, *, root: Path) -> list[Violation]:
    """Scan one Python file for exception-hygiene findings."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.as_posix()
    findings: list[Violation] = []
    scopes: list[str] = []

    class Visitor(ast.NodeVisitor):
        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            scopes.append(node.name)
            self.generic_visit(node)
            scopes.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            scopes.append(node.name)
            self.generic_visit(node)
            scopes.pop()

        def visit_Raise(self, node: ast.Raise) -> None:
            self.generic_visit(node)
            if _is_private_scope(scopes):
                return
            if node.exc is None or not isinstance(node.exc, ast.Call) or not node.exc.args:
                return
            text = _static_text(node.exc.args[0])
            if text is None:
                return
            evidence = _raise_evidence(text)
            if evidence is not None:
                findings.append(
                    Violation(
                        rule="raise-message",
                        path=relative,
                        scope=_scope_name(scopes),
                        evidence=evidence,
                        line=node.lineno,
                    )
                )

        def visit_Call(self, node: ast.Call) -> None:
            self.generic_visit(node)
            if _is_suppress(node) and not _has_silent_reason(lines, node.lineno):
                findings.append(
                    Violation(
                        rule="exception-suppress",
                        path=relative,
                        scope=_scope_name(scopes),
                        evidence="exception suppression requires '# silent: <reason>'",
                        line=node.lineno,
                    )
                )

        def visit_BoolOp(self, node: ast.BoolOp) -> None:
            self.generic_visit(node)
            loader = _masked_load_name(node)
            if loader is not None:
                findings.append(
                    Violation(
                        rule="masked-load-fallback",
                        path=relative,
                        scope=_scope_name(scopes),
                        evidence=f"{loader}(...) or {{}} masks load failures",
                        line=node.lineno,
                    )
                )

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            self.generic_visit(node)
            if (
                node.body
                and all(isinstance(item, ast.Pass | ast.Continue) for item in node.body)
                and not _has_silent_reason(lines, node.lineno)
            ):
                findings.append(
                    Violation(
                        rule="silent-handler",
                        path=relative,
                        scope=_scope_name(scopes),
                        evidence="pass/continue handler requires '# silent: <reason>'",
                        line=node.lineno,
                    )
                )

    Visitor().visit(tree)
    return findings


def scan(source: Path, *, root: Path) -> list[Violation]:
    """Scan a file or directory deterministically."""
    paths = [source] if source.is_file() else sorted(source.rglob("*.py"))
    findings = [item for path in paths for item in scan_file(path, root=root)]
    return sorted(findings)


def _load_baseline(path: Path) -> list[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(raw, dict) or not isinstance(raw.get("fingerprints"), list):
        raise TypeError(f"Invalid exception hygiene baseline {path}; expected a fingerprints list.")
    fingerprints = raw["fingerprints"]
    if not all(isinstance(item, str) for item in fingerprints):
        raise TypeError(f"Invalid exception hygiene baseline {path}; entries must be strings.")
    return sorted(fingerprints)


def _write_baseline(path: Path, findings: list[Violation]) -> None:
    payload = {
        "description": "Existing exception-hygiene debt; new or stale entries fail CI.",
        "fingerprints": sorted(item.fingerprint for item in findings),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Replace the baseline with the current semantic fingerprints.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path.cwd().resolve()
    source = args.source.resolve()
    baseline = args.baseline.resolve()
    findings = scan(source, root=root)

    if args.write_baseline:
        _write_baseline(baseline, findings)
        print(f"Wrote {len(findings)} exception-hygiene fingerprints to {baseline}.")
        return 0

    expected = _load_baseline(baseline)
    current = sorted(item.fingerprint for item in findings)
    expected_counts = Counter(expected)
    current_counts = Counter(current)
    new = current_counts - expected_counts
    stale = expected_counts - current_counts

    if new:
        by_fingerprint = {item.fingerprint: item for item in findings}
        print("New exception-hygiene violations:", file=sys.stderr)
        for fingerprint in sorted(new):
            count = new[fingerprint]
            suffix = f" ({count} occurrences)" if count > 1 else ""
            print(f"  {by_fingerprint[fingerprint].display()}{suffix}", file=sys.stderr)
    if stale:
        print("Stale exception-hygiene baseline entries:", file=sys.stderr)
        for fingerprint in sorted(stale):
            count = stale[fingerprint]
            suffix = f" ({count} occurrences)" if count > 1 else ""
            print(f"  {fingerprint}{suffix}", file=sys.stderr)
    if new or stale:
        print(
            "Fix the finding or run scripts/lint_exception_hygiene.py "
            "--write-baseline after deliberate review.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(findings)} known findings; no exception-hygiene drift.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
