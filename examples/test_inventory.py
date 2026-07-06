"""Regression proof for GitHub issue #501's authoritative example catalog."""

import pytest

from . import inventory as inventory_module
from .inventory import (
    EXAMPLES_ROOT,
    ExampleEntry,
    InventoryError,
    discover_runnable_examples,
    expected_readmes,
    load_inventory,
    validate_inventory,
)


@pytest.mark.issue(501)
def test_inventory_covers_every_runnable_example_exactly_once() -> None:
    entries = load_inventory()

    validate_inventory(entries)

    assert len(entries) == len(discover_runnable_examples())


@pytest.mark.issue(501)
def test_readme_inventory_tables_are_generated_from_manifest() -> None:
    entries = load_inventory()

    for path, expected in expected_readmes(entries).items():
        assert path.read_text(encoding="utf-8") == expected, (
            f"{path.relative_to(EXAMPLES_ROOT.parent)} is stale; run `python -m examples.inventory`"
        )


def test_inventory_reports_new_unrecorded_runnable_example(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = load_inventory()
    discovered = discover_runnable_examples() | {"standalone/unrecorded"}
    monkeypatch.setattr(inventory_module, "discover_runnable_examples", lambda: discovered)

    with pytest.raises(InventoryError, match="missing runnable examples: standalone/unrecorded"):
        validate_inventory(entries)


def test_inventory_reports_duplicate_paths() -> None:
    entries = load_inventory()

    with pytest.raises(InventoryError, match="duplicate example paths: chirpui/contacts_shell"):
        validate_inventory((*entries, entries[0]))


def test_inventory_reports_readme_status_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = ExampleEntry(
        path="standalone/hello",
        lane="standalone",
        status="canonical",
        tier=1,
        extras=(),
        network="none",
        capabilities=("routing",),
        readme="missing",
        test_entrypoint="examples/standalone/hello",
    )
    monkeypatch.setattr(
        inventory_module, "discover_runnable_examples", lambda: frozenset({entry.path})
    )

    with pytest.raises(InventoryError, match="README is present, inventory says missing"):
        validate_inventory((entry,))
