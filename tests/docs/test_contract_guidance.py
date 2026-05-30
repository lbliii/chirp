"""Guards for public contract-diagnostics guidance."""

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ROUTE_CONTRACT_DOC = (
    _ROOT / "site" / "content" / "docs" / "quality" / "contracts-debugging" / "route-contract.md"
)
_CATEGORY_REFERENCE_DOC = (
    _ROOT / "site" / "content" / "docs" / "quality" / "contracts-debugging" / "categories.md"
)
_CONTRACTS_SRC = _ROOT / "src" / "chirp" / "contracts"
_CATEGORY_LITERAL_RE = re.compile(r'category="([^"]+)"')
_CATEGORY_ROW_RE = re.compile(r"^\| `([^`]+)` \| ([^|]+) \|", re.MULTILINE)


def _route_contract_text() -> str:
    return _ROUTE_CONTRACT_DOC.read_text()


def _category_reference_text() -> str:
    return _CATEGORY_REFERENCE_DOC.read_text()


def _source_contract_categories() -> set[str]:
    categories: set[str] = set()
    for path in sorted(_CONTRACTS_SRC.rglob("*.py")):
        categories.update(_CATEGORY_LITERAL_RE.findall(path.read_text()))
    return categories


def _source_contract_severities() -> dict[str, set[str]]:
    severities: dict[str, set[str]] = {}
    for path in sorted(_CONTRACTS_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if func_name != "ContractIssue":
                continue

            category: str | None = None
            severity: str | None = None
            if len(node.args) >= 2:
                severity = _severity_name(node.args[0])
                if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    category = node.args[1].value

            for kw in node.keywords:
                if (
                    kw.arg == "category"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    category = kw.value.value
                elif kw.arg == "severity":
                    severity = _severity_name(kw.value)

            if category is not None and severity is not None:
                severities.setdefault(category, set()).add(severity)
    return severities


def _severity_name(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Severity"
    ):
        return node.attr
    return None


def _documented_category_severities() -> dict[str, set[str]]:
    rows: dict[str, set[str]] = {}
    for category, severity_text in _CATEGORY_ROW_RE.findall(_category_reference_text()):
        rows[category] = set(re.findall(r"\b(?:ERROR|WARNING|INFO)\b", severity_text))
    return rows


def test_route_contract_docs_name_diagnostic_fix_targets() -> None:
    text = _route_contract_text()

    assert "one concrete fix target" in text
    for target in (
        "route",
        "template",
        "block",
        "selector",
        "middleware",
        "config flag",
        "import string",
        "registration",
    ):
        assert target in text


def test_route_contract_docs_cover_recent_contract_categories() -> None:
    text = _route_contract_text()

    for category in (
        "page_handlers",
        "route_names",
        "mount_app_merge",
        "hx-target",
        "csrf_form",
    ):
        assert f"`{category}`" in text


def test_contract_category_reference_covers_source_categories() -> None:
    text = _category_reference_text()
    missing = sorted(
        category for category in _source_contract_categories() if f"`{category}`" not in text
    )

    assert missing == []


def test_contract_category_reference_documents_policy_hooks() -> None:
    text = _category_reference_text()

    assert "Default severity" in text
    assert "Fix target" in text
    assert "override_contract_severity" in text
    assert "--warnings-as-errors" in text


def test_contract_category_reference_matches_representative_source_severities() -> None:
    source = _source_contract_severities()
    documented = _documented_category_severities()

    for category in (
        "route_contract",
        "target",
        "context_cascade",
        "dead",
        "boundary",
        "live_block_unreachable_route",
        "debug_wiring",
        "chirpui_runtime",
        "command",
        "commandfor",
        "fragment",
        "page_shell",
        "htmx_partial",
        "sse",
        "component",
    ):
        assert documented[category] == source[category]


def test_contract_category_reference_uses_current_suspense_guidance() -> None:
    text = _category_reference_text()

    assert "`defer_falsy` | WARNING" in text
    assert "is deferred" in text
    assert "is not none" not in text
