"""Unit tests for the chirp-ui CSS-verify contract rule (#157)."""

from __future__ import annotations

import pytest

from chirp.contracts.rules_chirpui_css_verify import (
    _known_chirpui_css_classes,
    check_chirpui_css_verify,
)
from chirp.contracts.types import Severity

pytest.importorskip("chirp_ui")


class TestChirpuiCssVerifyRule:
    def test_unknown_chirpui_class_is_flagged_when_active(self) -> None:
        sources = {
            "page.html": '<div class="chirpui-card chirpui-cardd-typo">x</div>',
        }
        issues = check_chirpui_css_verify(sources, chirpui_active=True)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.WARNING
        assert issue.category == "chirpui_css_verify"
        assert issue.template == "page.html"
        assert "chirpui-cardd-typo" in issue.message

    def test_known_chirpui_class_is_silent(self) -> None:
        known = _known_chirpui_css_classes()
        assert known is not None
        sample = next(iter(known))
        sources = {"page.html": f'<div class="{sample}">x</div>'}
        assert check_chirpui_css_verify(sources, chirpui_active=True) == []

    def test_silent_when_chirpui_inactive(self) -> None:
        sources = {"page.html": '<div class="chirpui-cardd-typo">x</div>'}
        assert check_chirpui_css_verify(sources, chirpui_active=False) == []

    def test_framework_templates_are_skipped(self) -> None:
        sources = {"chirpui/card.html": '<div class="chirpui-cardd-typo">x</div>'}
        assert check_chirpui_css_verify(sources, chirpui_active=True) == []

    def test_does_not_flag_non_chirpui_classes(self) -> None:
        sources = {"page.html": '<div class="card typo-class">x</div>'}
        assert check_chirpui_css_verify(sources, chirpui_active=True) == []

    def test_does_not_match_longer_token(self) -> None:
        known = _known_chirpui_css_classes()
        assert known is not None
        sample = next(iter(known))
        if sample.endswith("-zone"):
            pytest.skip("no suitable known class for suffix test")
        sources = {"page.html": f'<div class="{sample}-zone">x</div>'}
        issues = check_chirpui_css_verify(sources, chirpui_active=True)
        assert len(issues) == 1
        assert f"{sample}-zone" in issues[0].details


@pytest.mark.issue(157)
def test_chirpui_css_verify_known_classes_loaded_from_package() -> None:
    known = _known_chirpui_css_classes()
    assert known is not None
    assert "chirpui-card" in known
    assert len(known) > 100
