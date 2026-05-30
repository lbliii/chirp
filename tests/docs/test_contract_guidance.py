"""Guards for public contract-diagnostics guidance."""

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


def _route_contract_text() -> str:
    return _ROUTE_CONTRACT_DOC.read_text()


def _category_reference_text() -> str:
    return _CATEGORY_REFERENCE_DOC.read_text()


def _source_contract_categories() -> set[str]:
    categories: set[str] = set()
    for path in sorted(_CONTRACTS_SRC.rglob("*.py")):
        categories.update(_CATEGORY_LITERAL_RE.findall(path.read_text()))
    return categories


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
