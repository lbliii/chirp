"""The checked-in diagnostic audit covers every core emission site."""

import ast
import hashlib
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _ROOT / "src" / "chirp" / "contracts"
_INVENTORY = _ROOT / "docs" / "contract-diagnostic-inventory.json"
_EMITTERS = _INVENTORY.with_suffix(".jsonl")


def _emitted_contract_issue_identities() -> list[list[str]]:
    """Build compact source identities without executing application code."""
    candidates: list[tuple[str, str, str, str, str]] = []
    for source_path in sorted(_CONTRACTS.rglob("*.py")):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        relative = source_path.relative_to(_ROOT).as_posix()
        issue_calls = sorted(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ContractIssue"
            ),
            key=lambda node: (node.lineno, node.col_offset),
        )
        for node in issue_calls:
            keywords = {item.arg: item.value for item in node.keywords if item.arg is not None}
            category = keywords.get("category")
            severity = keywords.get("severity")
            message = keywords.get("message")
            assert category is not None, f"{relative}:{node.lineno} omits category="
            assert severity is not None, f"{relative}:{node.lineno} omits severity="
            assert message is not None, f"{relative}:{node.lineno} omits message="
            message_expression = ast.unparse(message)
            candidates.append(
                (
                    relative,
                    ast.unparse(severity),
                    ast.unparse(category),
                    hashlib.sha256(message_expression.encode()).hexdigest(),
                    message_expression,
                )
            )
    occurrences: dict[tuple[str, str, str, str], int] = {}
    emitters: list[list[str]] = []
    for relative, severity, category, message_hash, message_expression in candidates:
        identity = (relative, severity, category, message_hash)
        occurrence = occurrences.get(identity, 0) + 1
        occurrences[identity] = occurrence
        stable_id = "|".join((*identity, str(occurrence)))
        emitters.append([stable_id, severity, category, message_hash, message_expression])
    return emitters


def test_contract_diagnostic_inventory_covers_every_emitting_site() -> None:
    inventory = json.loads(_INVENTORY.read_text(encoding="utf-8"))
    identities = _emitted_contract_issue_identities()
    recorded_emitters = [
        [row[field] for field in inventory["field_order"]]
        for line in _EMITTERS.read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))
    ]

    assert inventory["scope"].startswith("recursive ")
    assert inventory["family_assignment"] == (
        "Emitter rows carry explicit audit-family assignments; the AST test only guards source identity drift."
    )
    assert inventory["field_order"] == [
        "id",
        "severity_expression",
        "category_expression",
        "message_family_hash",
        "message_expression",
        "line",
        "audit_family",
    ]
    assert inventory["emitter_inventory"] == _EMITTERS.name
    assert inventory["emitter_count"] == len(identities)
    assert [row[:5] for row in recorded_emitters] == identities
    assert all(isinstance(row[5], int) and row[5] > 0 for row in recorded_emitters)

    families = inventory["audit_families"]
    assert {row[6] for row in recorded_emitters} == set(families)
    for profile in families.values():
        assert set(profile) == {
            "classification",
            "repair_surface",
            "repair_rationale",
            "uncertainty",
        }
        assert all(profile[field] for field in profile)
        assert profile["classification"] in {"actionable", "contextual"}

    assert not [
        row
        for row in recorded_emitters
        if row[1] == "Severity.ERROR" and families[row[6]]["classification"] == "contextual"
    ], "ERROR emitters require an actionable family or a documented exception."

    dynamic_rows = [row for row in recorded_emitters if not row[2].startswith(("'", '"'))]
    assert dynamic_rows
    assert {row[6] for row in dynamic_rows} == {"dynamic_category"}
    for rejected in ("ambiguous", "leaking", "duplicated", "missing_bounded_action"):
        assert rejected not in {profile["classification"] for profile in families.values()}
