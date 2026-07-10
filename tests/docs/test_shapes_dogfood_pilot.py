"""Decision-inventory checks for the Shapes dogfood pilot (#696)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "shapes-dogfood-pilot.md"
pytestmark = pytest.mark.issue(696)


def _report() -> str:
    return REPORT.read_text(encoding="utf-8")


def _prose() -> str:
    return " ".join(_report().split())


def test_pilot_records_baseline_and_all_three_slice_decisions() -> None:
    text = _report()

    assert "**Status:** Complete" in text
    assert "53499fa9eb6146a6019bdbd725c4f364a93baf8e" in text
    assert "| Sidebar-section CRUD | Retain application repository |" in text
    assert "| Tenant-scoped board list | Adopt narrowly |" in text
    assert "| Board summary read model | Retain application service/repository |" in text


def test_pilot_records_executed_correctness_typing_and_isolation_proof() -> None:
    text = _prose()

    assert "Receipt: `4 passed`" in text
    assert "3 passed All checks passed! # ty check" in text
    assert "same slug in two communities" in text
    assert "frozen and slotted and passed `ty`" in text
    assert "authorized community before passing `scope=`" in text


def test_pilot_preserves_crud_migration_and_computed_model_ownership() -> None:
    text = _prose()

    assert "Shapes exposes `SELECT` execution only" in text
    assert "The application repository remains authoritative" in text
    assert "The application service remains the correct owner" in text
    assert "Shapes does not own schema or migrations" in text
    assert "No PostgreSQL/Pelt claim follows from the SQLite pilot" in text


def test_pilot_rejects_speculative_framework_work_and_names_revisit_trigger() -> None:
    text = _prose()

    assert "No Chirp extension is justified by the pilot" in text
    assert "**Chirp:** no new issue" in text
    assert "**Pelt:** no issue" in text
    assert "PostgreSQL adoption or another product need" in text
    assert "No public API, runtime behavior, dependency, migration" in text
