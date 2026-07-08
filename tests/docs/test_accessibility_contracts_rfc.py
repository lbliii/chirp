"""Source-backed status checks for accessibility-contract RFC #346."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "017-accessibility-interaction-contracts.md"


@pytest.mark.issue(346)
def test_accessibility_rfc_is_explicitly_non_shipping() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Proposed" in text
    assert "does not add `chirp check --a11y strict`" in text
    assert "Changing existing accessibility severities in this RFC" in text
    assert "No changelog: proposed RFC only" in text


@pytest.mark.issue(346)
def test_accessibility_rfc_cites_current_rule_and_canary_evidence() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/contracts/rules_accessibility.py",
        "tests/contracts/test_accessibility.py",
        "tests/contracts/test_hypermedia.py",
        "src/chirp/contracts/rules_commands.py",
        "src/chirp/contracts/rules_swap.py",
        "src/chirp/app/hypermedia_program.py",
    ):
        assert path in text
    assert "254 templates" in text
    assert "273" in text


@pytest.mark.issue(346)
def test_accessibility_rfc_keeps_severity_and_runtime_gates_explicit() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "existing default remains `WARNING` for every category" in text
    assert "Only invalid explicit declarations should start as `ERROR`" in text
    assert "requires a separate implementation review" in text
    assert "zero false `ERROR`s" in text
