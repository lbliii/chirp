"""Executable documentation contract for RFC 015 structured inspection."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
RFC = ROOT / "docs" / "rfcs" / "015-structured-app-inspection.md"
pytestmark = pytest.mark.issue(510)


def _rfc() -> str:
    return RFC.read_text()


def _prose() -> str:
    return " ".join(_rfc().split())


def test_rfc_is_proposed_and_names_the_public_seam() -> None:
    text = _rfc()

    assert "**Status:** Proposed — no runtime behavior implemented" in text
    assert "App.inspect(*, deploy: bool = False) -> InspectionResult" in text
    assert "InspectionCounts" in text
    assert "InspectionLocation" in text


def test_rfc_separates_discovery_presentation_and_policy() -> None:
    text = _prose()

    assert "Discovery posture" in text
    assert "Presentation filtering" in text
    assert "Failure policy" in text
    assert "never accepts `warnings_as_errors`, `coverage`, or `include_info`" in text
    assert "It does not implicitly set warnings-as-errors in the Python API" in text


def test_rfc_preserves_cli_compatibility_and_versions_richer_json() -> None:
    text = _prose()

    assert "exact `chirp check --json` top-level shape" in text
    assert "ok, routes_checked, templates_scanned, issues" in text
    assert "schema_version" in text
    assert "include_timing=False" in text
    assert "cannot silently replace the default" in text


def test_rfc_defines_identity_origin_location_and_remediation() -> None:
    text = _prose()

    for field in (
        "finding_id",
        "subject_id",
        "location",
        "origin",
        "remediation",
        "identity_stability",
    ):
        assert field in text

    assert "never exports `HypermediaProgram`" in text
    assert "Absolute filesystem paths" in text


def test_rfc_defines_immutable_lifecycle_and_downstream_contract() -> None:
    text = _prose()

    assert "single finalization boundary" in text
    assert "frozen InspectionResult" in text
    assert "No result collection is shared between calls" in text
    assert "capture stdout/stderr" in text
    assert "catch `SystemExit`" in text


def test_rfc_covers_proof_collateral_and_steward_synthesis() -> None:
    text = _rfc()

    for heading in (
        "## 13. Required proof",
        "## 14. Public API and collateral contract",
        "## 17. Steward synthesis",
        "### Convergence",
        "### Minority reports",
        "### Ranked implementation backlog",
        "## 18. Global sweep for accepted P0s",
    ):
        assert heading in text

    assert text.count("Steward:") >= 5
    assert text.count("Verification Status:") >= 5
    assert text.count("machine-verified") >= 5
