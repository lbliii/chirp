"""Guards for public contract-diagnostics guidance."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ROUTE_CONTRACT_DOC = (
    _ROOT / "site" / "content" / "docs" / "quality" / "contracts-debugging" / "route-contract.md"
)


def _route_contract_text() -> str:
    return _ROUTE_CONTRACT_DOC.read_text()


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
