"""Unit proof for the bounded live-preserving template reload planner."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.templating.dev_template_reload import (
    TemplateReloadEntry,
    TemplateReloadInventory,
    TemplateReloadPlanner,
    TemplateReloadSurface,
    TemplateReloadTarget,
)

pytestmark = pytest.mark.issue(341)


def _write_two_blocks(path: Path, *, first: str = "one", include_second: bool = True) -> None:
    second = "{% block second %}stable{% end %}" if include_second else ""
    path.write_text(f"{{% block first %}}{first}{{% end %}}{second}", encoding="utf-8")


def _planner(path: Path, *, targets: tuple[TemplateReloadTarget, ...] | None = None):
    env = Environment(loader=FileSystemLoader(str(path.parent)), auto_reload=True)
    manifest = env.get_template_structure(path.name)
    assert manifest is not None
    entry = TemplateReloadEntry(
        template_name=path.name,
        source_filename=str(path.resolve()),
        extends=manifest.extends,
        blocks=tuple(sorted(manifest.block_hashes.items())),
        dependencies=frozenset(manifest.dependencies),
        route_paths=("/",),
        targets=targets
        if targets is not None
        else (TemplateReloadTarget("main", "first", "content"),),
    )
    return TemplateReloadPlanner(env, TemplateReloadInventory((entry,)))


def _eligible_surface(**changes) -> TemplateReloadSurface:
    values = {
        "reachable_templates": frozenset({"page.html"}),
        "route_target_ids": frozenset({"main"}),
        "live_target_counts": (("main", 1),),
        "get_safe": True,
        "htmx_adapter_available": True,
    }
    values.update(changes)
    return TemplateReloadSurface(**values)


def test_changed_block_hash_isolated_after_explicit_kida_invalidation(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    _write_two_blocks(path)
    planner = _planner(path)
    before = planner.inventory.entries[0].block_hashes

    _write_two_blocks(path, first="changed")
    plan = planner.plan_edit(path, _eligible_surface())
    after = planner.inventory.entries[0].block_hashes

    assert plan.outcome == "patch"
    assert plan.reason == "registered_live_target"
    assert plan.changed_blocks == ("first",)
    assert plan.target_id == "main"
    assert plan.requires_response_validation is True
    assert before["first"] != after["first"]
    assert before["second"] == after["second"]


@pytest.mark.parametrize(
    ("edit", "reason", "added", "removed"),
    [
        ("add", "block_added", ("third",), ()),
        ("remove", "block_removed", (), ("second",)),
    ],
)
def test_added_and_removed_blocks_are_classified_separately(
    tmp_path: Path,
    edit: str,
    reason: str,
    added: tuple[str, ...],
    removed: tuple[str, ...],
) -> None:
    path = tmp_path / "page.html"
    _write_two_blocks(path)
    planner = _planner(path)
    if edit == "add":
        path.write_text(
            path.read_text(encoding="utf-8") + "{% block third %}new{% end %}",
            encoding="utf-8",
        )
    else:
        _write_two_blocks(path, include_second=False)

    plan = planner.plan_edit(path, _eligible_surface())

    assert plan.outcome == "reload"
    assert plan.reason == reason
    assert plan.added_blocks == added
    assert plan.removed_blocks == removed


def test_parent_template_change_forces_composition_reload(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    _write_two_blocks(path)
    (tmp_path / "base.html").write_text(
        "{% block first %}base{% end %}{% block second %}base{% end %}",
        encoding="utf-8",
    )
    planner = _planner(path)
    path.write_text(
        '{% extends "base.html" %}'
        "{% block first %}changed{% end %}"
        "{% block second %}stable{% end %}",
        encoding="utf-8",
    )

    plan = planner.plan_edit(path, _eligible_surface())

    assert plan.outcome == "reload"
    assert plan.reason == "composition_changed"


def test_broken_template_diagnoses_without_payload_or_snapshot_publication(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    _write_two_blocks(path)
    planner = _planner(path)
    previous = planner.inventory
    path.write_text("{% block first %}broken", encoding="utf-8")

    plan = planner.plan_edit(path, _eligible_surface())

    assert plan.outcome == "diagnose"
    assert plan.reason == "template_compile_error"
    assert plan.error_type == "ParseError"
    assert plan.target_id is None
    assert plan.requires_response_validation is False
    assert planner.inventory is previous
    assert not hasattr(plan, "html")
    assert not hasattr(plan, "context")


@pytest.mark.parametrize(
    ("surface_changes", "targets", "reason"),
    [
        ({"reachable_templates": frozenset()}, None, "not_current_route_template"),
        ({}, (), "target_unregistered"),
        ({"route_target_ids": frozenset()}, None, "target_outside_route_scope"),
        ({"live_target_counts": ()}, None, "target_missing"),
        ({"live_target_counts": (("main", 2),)}, None, "target_duplicate"),
        ({"connection_boundary_targets": frozenset({"main"})}, None, "connection_boundary"),
        ({"shell_boundary_targets": frozenset({"main"})}, None, "shell_boundary"),
        ({"active_suspense_targets": frozenset({"main"})}, None, "active_suspense"),
        ({"get_safe": False}, None, "route_not_safe_get"),
        ({"htmx_adapter_available": False}, None, "htmx_adapter_unavailable"),
    ],
)
def test_patch_eligibility_fails_closed(
    tmp_path: Path,
    surface_changes: dict,
    targets: tuple[TemplateReloadTarget, ...] | None,
    reason: str,
) -> None:
    path = tmp_path / "page.html"
    _write_two_blocks(path)
    planner = _planner(path, targets=targets)
    _write_two_blocks(path, first="changed")

    plan = planner.plan_edit(path, _eligible_surface(**surface_changes))

    assert plan.outcome == "reload"
    assert plan.reason == reason
    assert plan.requires_response_validation is False


def test_duplicate_route_targets_are_ambiguous(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    _write_two_blocks(path)
    planner = _planner(
        path,
        targets=(
            TemplateReloadTarget("main", "first", "shell"),
            TemplateReloadTarget("other", "first", "content"),
        ),
    )
    _write_two_blocks(path, first="changed")
    surface = _eligible_surface(
        route_target_ids=frozenset({"main", "other"}),
        live_target_counts=(("main", 1), ("other", 1)),
    )

    plan = planner.plan_edit(path, surface)

    assert plan.outcome == "reload"
    assert plan.reason == "target_ambiguous"


def test_unknown_edits_receive_unique_monotonic_revisions_under_threads(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    _write_two_blocks(path)
    planner = _planner(path)
    unknown = tmp_path / "component.html"

    with ThreadPoolExecutor(max_workers=8) as executor:
        plans = list(
            executor.map(
                lambda _index: planner.plan_edit(unknown, TemplateReloadSurface()),
                range(40),
            )
        )

    assert {plan.revision for plan in plans} == set(range(1, 41))
    assert {plan.reason for plan in plans} == {"unknown_template_source"}
    assert {plan.outcome for plan in plans} == {"reload"}
