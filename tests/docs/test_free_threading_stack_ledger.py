"""Drift guards for the Bengal stack free-threading ledger (#944)."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LEDGER = _ROOT / "docs" / "design" / "free-threading-stack-ledger.md"
_THREAD_SAFETY = _ROOT / "site" / "content" / "docs" / "about" / "thread-safety.md"
_PELT_EVIDENCE = _ROOT / "docs" / "pelt-free-threading.md"
_STACK_TEST = _ROOT / "tests" / "interop" / "test_free_threading_stack.py"


@pytest.mark.issue(944)
def test_stack_ledger_names_shared_vs_isolated_contract() -> None:
    text = _LEDGER.read_text(encoding="utf-8")

    for needle in (
        "Shared warm",
        "Isolated",
        "Startup-only mutation",
        "Chirp",
        "Kida",
        "Pounce",
        "Pelt",
        "Honest boundaries",
        "App-owned mutable context",
        "tests/interop/test_free_threading_stack.py",
        "PYTHON_GIL=0",
    ):
        assert needle in text


@pytest.mark.issue(944)
def test_thread_safety_docs_link_the_stack_ledger() -> None:
    thread_safety = _THREAD_SAFETY.read_text(encoding="utf-8")
    pelt = _PELT_EVIDENCE.read_text(encoding="utf-8")
    ledger_ref = "docs/design/free-threading-stack-ledger.md"

    assert ledger_ref in thread_safety
    assert ledger_ref in pelt


@pytest.mark.issue(944)
def test_stack_integration_test_is_issue_tagged() -> None:
    text = _STACK_TEST.read_text(encoding="utf-8")
    assert "@pytest.mark.issue(944)" in text
    assert "TestServer" in text
    assert "Pool" in text
    assert "Template" in text
