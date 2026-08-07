"""Docs lock for MCP 2026-07-28 stateless transport + SEP-2243 headers (#968)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.issue(968)

_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_DOC = _ROOT / "site" / "content" / "docs" / "build-apps" / "ui-extensions" / "tools.md"
_PUBLIC_API_DOC = _ROOT / "docs" / "public-api.md"


def test_tools_guide_documents_stateless_transport_and_routing_headers() -> None:
    docs = _TOOLS_DOC.read_text(encoding="utf-8")

    for required in (
        "2026-07-28",
        "stateless",
        "params._meta",
        "server/discover",
        "MCP-Protocol-Version",
        "Mcp-Method",
        "Mcp-Name",
        "HeaderMismatch",
        "-32020",
        "SEP-2243",
    ):
        assert required in docs, f"missing {required!r} in {_TOOLS_DOC.relative_to(_ROOT)}"


def test_public_api_audit_mentions_stateless_mcp_headers() -> None:
    docs = _PUBLIC_API_DOC.read_text(encoding="utf-8")

    for required in (
        "2026-07-28",
        "params._meta",
        "MCP-Protocol-Version",
        "Mcp-Method",
        "Mcp-Name",
        "HeaderMismatch",
        "-32020",
    ):
        assert required in docs, f"missing {required!r} in docs/public-api.md"
