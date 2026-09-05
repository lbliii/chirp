"""Audit classified private Chirp access in pinned downstream source trees.

This is maintainer tooling, not a public framework API. Static provenance comes
from Chirp imports, annotations, constructor calls, aliases, and reviewed receiver
hints in the ledger. Unknown Python objects are not presumed to be Chirp objects.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path(__file__).with_name("private_api_ledger.json")
CLASSIFICATIONS = frozenset(
    {"framework-defect", "missing-public-seam", "diagnostics-gap", "app-owned", "test-only"}
)


def _private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else None
    return None


@dataclass(frozen=True)
class Finding:
    path: str
    scope: str
    kind: str
    symbol: str
    line: int

    @property
    def key(self) -> str:
        return "|".join((self.path, self.scope, self.kind, self.symbol))


class Scanner(ast.NodeVisitor):
    def __init__(self, path: str, hints: list[dict[str, str]]) -> None:
        self.path = path
        self.hints = hints
        self.scope: list[str] = []
        self.seen_scopes = {""}
        self.bindings: dict[str, str] = {}
        self.returns: dict[str, str] = {}
        self.findings: list[Finding] = []

    def origin(self, node: ast.AST | None) -> str | None:
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                return self.origin(ast.parse(node.value, mode="eval").body)
            except SyntaxError:
                return None
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
            ):
                name = node.args[1]
                base = self.origin(node.args[0])
                if base and isinstance(name, ast.Constant) and isinstance(name.value, str):
                    return f"{base}.{name.value}"
            dotted = _dotted(node.func)
            return self.returns.get(dotted or "") or self.origin(node.func)
        dotted = _dotted(node)
        if dotted:
            for key in sorted(self.bindings, key=len, reverse=True):
                if dotted == key or dotted.startswith(key + "."):
                    return self.bindings[key] + dotted[len(key) :]
        if isinstance(node, ast.Attribute) and (base := self.origin(node.value)):
            return f"{base}.{node.attr}"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self.origin(node.left) or self.origin(node.right)
        return None

    def record(self, node: ast.AST, kind: str, symbol: str) -> None:
        if symbol.startswith("chirp."):
            self.findings.append(
                Finding(self.path, ".".join(self.scope), kind, symbol, node.lineno)
            )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bindings.pop(alias.asname or alias.name.split(".")[0], None)
            if alias.name == "chirp" or alias.name.startswith("chirp."):
                self.bindings[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else "chirp"
                )
                if any(_private(part) for part in alias.name.split(".")):
                    self.record(node, "import", alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bindings.pop(alias.asname or alias.name, None)
        if not node.level and (node.module == "chirp" or (node.module or "").startswith("chirp.")):
            for alias in node.names:
                symbol = f"{node.module}.{alias.name}"
                self.bindings[alias.asname or alias.name] = symbol
                if any(_private(part) for part in symbol.split(".")):
                    self.record(node, "import", symbol)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            _private(node.attr)
            and (origin := self.origin(node))
            and origin.endswith("." + node.attr)
        ):
            self.record(node, "attribute", origin)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "setattr", "hasattr"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
        ):
            name = node.args[1].value
            origin = self.origin(node.args[0])
            if isinstance(name, str) and _private(name) and origin:
                self.record(node, "dynamic-attribute", f"{origin}.{name}")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        # Monkeypatches using vars(chirp_module)["name"] also need an owner,
        # even when the patched implementation function has no underscore.
        if isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "vars" and len(call.args) == 1:
                origin = self.origin(call.args[0])
                if (
                    origin
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)
                ):
                    self.record(node, "module-patch", f"{origin}.{node.slice.value}")
        self.generic_visit(node)

    def _bind(self, target: ast.AST, origin: str | None) -> None:
        name = _dotted(target)
        if name:
            if origin:
                self.bindings[name] = origin
            else:
                self.bindings.pop(name, None)
                self._hints()

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        origin = self.origin(node.value)
        for target in node.targets:
            self._bind(target, origin)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        self._bind(node.target, self.origin(node.annotation) or self.origin(node.value))

    def _hints(self) -> None:
        scope = ".".join(self.scope)
        for hint in self.hints:
            if hint["scope"] == scope or scope.startswith(hint["scope"] + "."):
                self.bindings[hint["receiver"]] = hint["origin"]

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # Definition headers execute in the enclosing scope, before parameters
        # shadow imported names. They are private accesses too.
        for header in [*node.decorator_list, node.args, *node.type_params]:
            self.visit(header)
        if node.returns is not None:
            self.visit(node.returns)
        bindings, returns = self.bindings.copy(), self.returns.copy()
        self.scope.append(node.name)
        self.seen_scopes.add(".".join(self.scope))
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            self._bind(ast.Name(id=arg.arg), self.origin(arg.annotation))
        self._hints()
        for child in node.body:
            self.visit(child)
        self.scope.pop()
        self.bindings, self.returns = bindings, returns

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def _body(self, body: list[ast.stmt]) -> None:
        # Imports and return annotations describe local factory provenance even
        # when a factory is defined below its caller. No application is executed.
        for node in body:
            if isinstance(node, ast.Import | ast.ImportFrom):
                self.visit(node)
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and (
                origin := self.origin(node.returns)
            ):
                self.returns[node.name] = origin
                self.returns[f"self.{node.name}"] = origin
        self._hints()
        for node in body:
            if not isinstance(node, ast.Import | ast.ImportFrom):
                self.visit(node)

    def visit_Module(self, node: ast.Module) -> None:
        self._body(node.body)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for header in [*node.decorator_list, *node.bases, *node.keywords, *node.type_params]:
            self.visit(header)
        bindings, returns = self.bindings.copy(), self.returns.copy()
        self.scope.append(node.name)
        self.seen_scopes.add(".".join(self.scope))
        self._body(node.body)
        self.scope.pop()
        self.bindings, self.returns = bindings, returns


def scan_source(source: str, path: str, hints: list[dict[str, str]] | None = None) -> list[Finding]:
    scanner = Scanner(path, hints or [])
    scanner.visit(ast.parse(source, filename=path))
    for hint in hints or []:
        if hint["scope"] not in scanner.seen_scopes:
            msg = f"{path}: reviewed receiver scope {hint['scope']!r} no longer exists; update its ledger evidence."
            raise ValueError(msg)
    return sorted(scanner.findings, key=lambda row: (row.key, row.line))


def scan_repository(root: Path, repository: dict[str, Any]) -> list[Finding]:
    files = subprocess.check_output(["git", "ls-files", "*.py"], cwd=root, text=True).splitlines()
    hints = repository.get("receivers", [])
    for hint in hints:
        if hint["path"] not in files:
            msg = f"Reviewed receiver file {hint['path']!r} is missing; update its ledger evidence."
            raise ValueError(msg)
    findings = []
    for path in files:
        findings.extend(
            scan_source((root / path).read_text(), path, [h for h in hints if h["path"] == path])
        )
    return findings


def _test_path(path: str) -> bool:
    return any(part in {"tests", "test"} for part in Path(path).parts) or Path(
        path
    ).name.startswith("test_")


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    errors = []
    if ledger.get("schema_version") != 1:
        errors.append("Expected private API ledger schema_version 1.")
    repositories = ledger.get("repositories", {})
    if set(repositories) != {"elbysodic", "furatena", "showrun", "pidge", "orrery"}:
        errors.append("Ledger must include all five first-party repositories.")
    for name, repository in repositories.items():
        if repository.get("repository") != f"lbliii/{name}":
            errors.append(f"{name}: repository identity must match the audited first-party source.")
        revision = repository.get("revision", "")
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            errors.append(f"{name}: expected exact 40-character source revision.")
        keys = set()
        for finding in repository.get("findings", []):
            key = finding.get("key", "")
            if key in keys:
                errors.append(f"{name}: duplicate finding {key}.")
            keys.add(key)
            if finding.get("classification") not in CLASSIFICATIONS:
                errors.append(f"{name}: {key}: missing valid classification.")
            errors.extend(
                f"{name}: {key}: missing {field}."
                for field in ("owner", "rationale", "follow_up", "source")
                if not finding.get(field)
            )
            prefix = f"https://github.com/{repository['repository']}/blob/{revision}/"
            if not finding.get("source", "").startswith(prefix):
                errors.append(f"{name}: {key}: source must link the pinned revision.")
            if finding.get("classification") == "test-only" and not _test_path(key.split("|")[0]):
                errors.append(
                    f"{name}: production access cannot use test-only classification: {key}."
                )
            if type(finding.get("count")) is not int or finding["count"] < 1:
                errors.append(f"{name}: {key}: count must be positive.")
        prefix = f"https://github.com/{repository['repository']}/blob/{revision}/"
        errors.extend(
            f"{name}: manual decisions require classification, ownership, follow-up, and pinned source."
            for decision in repository.get("manual_decisions", [])
            if decision.get("classification") not in CLASSIFICATIONS
            or not all(
                decision.get(field) for field in ("operation", "owner", "rationale", "follow_up")
            )
            or not decision.get("source", "").startswith(prefix)
        )
        errors.extend(
            f"{name}: receiver hints require Chirp origin and pinned source evidence."
            for hint in repository.get("receivers", [])
            if not hint.get("evidence", "").startswith(prefix)
            or not hint.get("origin", "").startswith("chirp.")
            or not hint.get("rationale")
        )
    return errors


def check_repository(root: Path, repository: dict[str, Any]) -> list[str]:
    findings = scan_repository(root, repository)
    expected = {row["key"]: row for row in repository["findings"]}
    counts = Counter(row.key for row in findings if not _test_path(row.path))
    errors = []
    for finding in findings:
        if _test_path(finding.path):
            continue  # Explicit test-only inspection policy; never a blanket test ban.
        row = expected.get(finding.key)
        if row is None or counts[finding.key] > row["count"]:
            errors.append(
                f"{finding.path}:{finding.line}: unclassified production Chirp access "
                f"{finding.symbol} ({finding.scope}). Classify {finding.key!r} in "
                "scripts/private_api_ledger.json with an owner, rationale, and follow-up."
            )
    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--repo", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument(
        "--pinned", action="store_true", help="Require the audited source revisions."
    )
    args = parser.parse_args(argv)
    ledger = json.loads(args.ledger.read_text())
    errors = validate_ledger(ledger)
    for spec in args.repo:
        name, separator, directory = spec.partition("=")
        if not separator or name not in ledger["repositories"]:
            errors.append(f"Unknown repository mapping {spec!r}; use NAME=PATH from the ledger.")
            continue
        repository = ledger["repositories"][name]
        if args.pinned:
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=directory, text=True
            ).strip()
            if revision != repository["revision"]:
                errors.append(f"{name}: checked-out revision differs from the audited source pin.")
                continue
        try:
            errors.extend(check_repository(Path(directory), repository))
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.matrix:
        print(
            json.dumps(
                {
                    "include": [
                        {
                            "name": name,
                            "repository": repo["repository"],
                            "revision": repo["revision"],
                        }
                        for name, repo in ledger["repositories"].items()
                    ]
                }
            )
        )
    else:
        print("Private API ledger and requested production-source ratchets passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
