"""Machine-readable canary and decision receipt for accessibility issue #686."""

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RECEIPT = Path(__file__).with_name("a11y_interaction_evidence.json")
_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_PATTERNS = {
    "focus_request_tags": re.compile(
        r"<[^>]+\bhx-(?:get|post|put|patch|delete)\b[^>]*>", re.IGNORECASE | re.DOTALL
    ),
    "live_update_markers": re.compile(r"\b(?:sse-swap|hx-swap-oob)\b", re.IGNORECASE),
    "live_policy_markers": re.compile(
        r"\baria-live\b|\brole\s*=\s*[\"'](?:status|log|alert)[\"']", re.IGNORECASE
    ),
    "dialogs": re.compile(r"<dialog\b", re.IGNORECASE),
    "popovers": re.compile(r"\bpopover(?:target)?\b", re.IGNORECASE),
    "reduced_motion_markers": re.compile(r"prefers-reduced-motion|view-transition", re.IGNORECASE),
}


def _receipt() -> dict:
    return json.loads(_RECEIPT.read_text(encoding="utf-8"))


def _candidate_counts(root: Path) -> dict[str, int]:
    sources = tuple(
        _COMMENT.sub("", path.read_text(encoding="utf-8")) for path in root.rglob("*.html")
    )
    return {
        name: sum(len(pattern.findall(source)) for source in sources)
        for name, pattern in _PATTERNS.items()
    }


@pytest.mark.issue(686)
def test_decision_receipt_covers_every_family_and_false_result_boundary() -> None:
    receipt = _receipt()
    assert receipt["schema_version"] == 1
    assert receipt["issue"] == 686
    assert set(receipt["families"]) == {
        "focus_continuity",
        "live_region",
        "dialog_popover",
        "reduced_motion",
    }
    assert {family["decision"] for family in receipt["families"].values()} <= {
        "accept",
        "revise",
        "no-go",
    }
    for family in receipt["families"].values():
        assert family["known_false_negative"]
        assert family["false_positive_boundary"]
        assert family["next_gate"]


@pytest.mark.issue(686)
@pytest.mark.parametrize("canary", ["lucky_cat", "forum_shell"])
def test_canary_candidate_receipt_fails_when_template_inventory_drifts(canary: str) -> None:
    entry = _receipt()["canaries"][canary]
    assert _candidate_counts(_ROOT / entry["root"]) == entry["candidate_counts"]
    assert entry["existing_a11y_findings"] == 0
    assert entry["classification"]
