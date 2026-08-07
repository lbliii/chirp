"""Regenerate docs/contract-diagnostic-inventory.{json,jsonl} from source AST."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "src" / "chirp" / "contracts"
INVENTORY = ROOT / "docs" / "contract-diagnostic-inventory.json"
EMITTERS = INVENTORY.with_suffix(".jsonl")

FIELD_ORDER = [
    "id",
    "severity_expression",
    "category_expression",
    "message_family_hash",
    "message_expression",
    "line",
    "audit_family",
]


def build_candidates():
    candidates = []
    for source_path in sorted(CONTRACTS.rglob("*.py")):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        relative = source_path.relative_to(ROOT).as_posix()
        issue_calls = sorted(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "ContractIssue"
            ),
            key=lambda n: (n.lineno, n.col_offset),
        )
        for node in issue_calls:
            kw = {i.arg: i.value for i in node.keywords if i.arg is not None}
            category = kw.get("category")
            severity = kw.get("severity")
            message = kw.get("message")
            if category is None or severity is None or message is None:
                raise ValueError(
                    f"{relative}:{node.lineno} ContractIssue omits category/severity/message"
                )
            message_expression = ast.unparse(message)
            candidates.append(
                (
                    relative,
                    ast.unparse(severity),
                    ast.unparse(category),
                    hashlib.sha256(message_expression.encode()).hexdigest(),
                    message_expression,
                    node.lineno,
                )
            )
    return candidates


def main():
    candidates = build_candidates()
    occurrences = {}
    new_rows = []
    for relative, severity, category, message_hash, message_expression, lineno in candidates:
        identity = (relative, severity, category, message_hash)
        occ = occurrences.get(identity, 0) + 1
        occurrences[identity] = occ
        stable_id = "|".join((*identity, str(occ)))
        row_obj = {}
        row_obj["id"] = stable_id
        row_obj["severity_expression"] = severity
        row_obj["category_expression"] = category
        row_obj["message_family_hash"] = message_hash
        row_obj["message_expression"] = message_expression
        row_obj["line"] = lineno
        row_obj["audit_family"] = None
        row_obj["_match"] = (relative, severity, category, occ)
        new_rows.append(row_obj)

    old_family = {}
    for line in EMITTERS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        parts = row["id"].split("|")
        key = (parts[0], parts[1], parts[2], int(parts[4]))
        old_family[key] = row["audit_family"]

    missing = []
    for r in new_rows:
        fam = old_family.get(r["_match"])
        if fam is None:
            missing.append(r["_match"])
        r["audit_family"] = fam
    if missing:
        raise SystemExit("New emitters have no audit_family: " + repr(missing))

    with EMITTERS.open("w", encoding="utf-8") as f:
        for r in new_rows:
            out = {k: r[k] for k in FIELD_ORDER}
            f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
    inv["emitter_count"] = len(new_rows)
    INVENTORY.write_text(json.dumps(inv, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("regenerated", len(new_rows), "emitters; emitter_count=", inv["emitter_count"])


if __name__ == "__main__":
    main()
