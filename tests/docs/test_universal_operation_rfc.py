"""Executable contract checks for RFC 014's universal-operation boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
RFC = ROOT / "docs" / "rfcs" / "014-universal-operation.md"
pytestmark = pytest.mark.issue(339)


def _rfc() -> str:
    return RFC.read_text()


def _prose() -> str:
    return " ".join(_rfc().split())


def test_rfc_records_implemented_slice_and_pins_external_evidence() -> None:
    text = _rfc()

    assert "**Status:** Accepted — declarative WebMCP form preview, Milo MCP Apps" in text
    assert "1f5370861fa38bc7942111a623fa2cb5a7f567b9" in text
    assert "0b676d27a08aafd3b4f8a709756eeeab342fd9bd" in text
    assert "Milo's open MCP Apps boundary issue" in text


@pytest.mark.issue(577)
def test_rfc_records_the_milo_registration_only_slice() -> None:
    text = _prose()

    assert "`milo-cli>=0.4.1,<0.5`" in text
    assert "`use_milo(app, cli, allowlist=(...))`" in text
    assert "matching `ui=MCPAppToolMeta(resource_uri=...)`" in text
    assert "explicit parameterless application context provider" in text
    assert "neither freezes nor mutates the caller-owned Milo `CLI`" in text
    assert "No ambient Chirp `Request`, session, Milo context" in text
    assert "Issue #578 adds `MiloMCPAppAdapter.render_resource()`" in text


@pytest.mark.issue(578)
def test_rfc_records_named_block_resource_rendering() -> None:
    text = _prose()

    assert "`MiloMCPAppAdapter.render_resource()`" in text
    assert "named-block rendering through the existing render surface" in text
    assert "Read-only sandbox, CSP, and host auth semantics remain pending" in text


def test_rfc_covers_every_required_projection() -> None:
    text = _rfc()

    for surface in (
        "Browser HTTP",
        "htmx",
        "Human CLI",
        "Programmatic CLI",
        "MCP tool",
        "WebMCP",
        "MCP App",
    ):
        assert surface in text


def test_rfc_preserves_hypermedia_and_explicit_exposure_invariants() -> None:
    text = _prose()

    assert "does not introduce a second operation" in text
    assert "HTML is never inferred from `outputSchema`" in text
    assert "Every projection is independently opt-in" in text
    assert "missing required block raises `BlockNotFoundError`" in text
    assert "must not close that gap with a generic serializer" in text
    assert "No automatic route, tool, WebMCP, or MCP App exposure" in text


def test_rfc_defines_context_and_execution_tiers() -> None:
    text = _prose()

    assert "Chirp Request and Milo Context stay distinct" in text
    assert "first tier accepts synchronous, finite callables" in text
    assert "Async universal operations are **not supported**" in text
    assert "first tier rejects generator and async-generator operations" in text


def test_rfc_defines_exact_webmcp_preview_boundary() -> None:
    text = _prose()

    for attribute in (
        "`toolname`",
        "`tooldescription`",
        "`toolparamdescription`",
        "`toolautosubmit`",
    ):
        assert attribute in text

    assert "mutation, destructive command" in text
    assert "must omit `toolautosubmit`" in text
    assert "does not use `document.modelContext.registerTool()`" in text


def test_rfc_names_proof_collateral_and_steward_synthesis() -> None:
    text = _rfc()

    for heading in (
        "## 14. Contract checks and diagnostics",
        "## 15. Canonical prototype: create a work item",
        "## 16. Public API and collateral contract",
        "## 17. Compatibility gates and dependencies",
        "## 20. Steward synthesis",
        "### Convergence",
        "### Minority reports",
        "### Ranked implementation backlog",
    ):
        assert heading in text

    assert text.count("Steward:") >= 5
    assert text.count("Verification Status:") >= 5
    assert text.count("machine-verified") >= 5
