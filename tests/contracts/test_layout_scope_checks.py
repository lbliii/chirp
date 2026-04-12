"""Tests for hierarchical shell scope contract checks (Phase 4 of RFC)."""

from __future__ import annotations

from chirp.contracts.rules_layout import check_layout_chains
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.fragment_target_registry import FragmentTargetRegistry


def _make_registry(*target_ids: str) -> FragmentTargetRegistry:
    reg = FragmentTargetRegistry()
    for tid in target_ids:
        reg.register(tid, fragment_block=f"{tid}_block")
    reg.freeze()
    return reg


# --- outlet_target_id checks ---


def test_outlet_target_id_found_in_templates() -> None:
    layout = LayoutInfo("root.html", "body", 0, outlet_target_id="site-content")
    chain = LayoutChain((layout,))
    sources = {"root.html": '<div id="site-content">{% block content %}{% end %}</div>'}
    issues = check_layout_chains([chain], sources)
    outlet_issues = [i for i in issues if i.category == "layout_outlet"]
    assert not outlet_issues


def test_outlet_target_id_missing_warns() -> None:
    layout = LayoutInfo("root.html", "body", 0, outlet_target_id="site-content")
    chain = LayoutChain((layout,))
    sources = {"root.html": '<div id="main">{% block content %}{% end %}</div>'}
    issues = check_layout_chains([chain], sources)
    outlet_issues = [i for i in issues if i.category == "layout_outlet"]
    assert len(outlet_issues) == 1
    assert "site-content" in outlet_issues[0].message


def test_outlet_target_id_found_in_other_template() -> None:
    layout = LayoutInfo("root.html", "body", 0, outlet_target_id="app-content")
    chain = LayoutChain((layout,))
    sources = {
        "root.html": "{% block content %}{% end %}",
        "chirpui/app_shell.html": '<main id="app-content">',
    }
    issues = check_layout_chains([chain], sources)
    outlet_issues = [i for i in issues if i.category == "layout_outlet"]
    assert not outlet_issues


# --- outlet not registered as fragment target ---


def test_outlet_not_registered_warns() -> None:
    layout = LayoutInfo("root.html", "body", 0, outlet_target_id="site-content")
    chain = LayoutChain((layout,))
    sources = {"root.html": '<div id="site-content">{% block content %}{% end %}</div>'}
    reg = _make_registry("main", "page-root")
    issues = check_layout_chains([chain], sources, fragment_target_registry=reg)
    outlet_issues = [i for i in issues if "not registered as a fragment target" in i.message]
    assert len(outlet_issues) == 1
    assert "site-content" in outlet_issues[0].message
    assert "register_fragment_target" in outlet_issues[0].message


def test_outlet_registered_no_warning() -> None:
    layout = LayoutInfo("root.html", "body", 0, outlet_target_id="site-content")
    chain = LayoutChain((layout,))
    sources = {"root.html": '<div id="site-content">{% block content %}{% end %}</div>'}
    reg = _make_registry("site-content", "main")
    issues = check_layout_chains([chain], sources, fragment_target_registry=reg)
    outlet_issues = [i for i in issues if "not registered as a fragment target" in i.message]
    assert not outlet_issues


def test_outlet_registration_check_skipped_without_registry() -> None:
    layout = LayoutInfo("root.html", "body", 0, outlet_target_id="site-content")
    chain = LayoutChain((layout,))
    sources = {"root.html": '<div id="site-content">{% block content %}{% end %}</div>'}
    issues = check_layout_chains([chain], sources)
    outlet_issues = [i for i in issues if "not registered as a fragment target" in i.message]
    assert not outlet_issues


# --- frame_targets checks ---


def test_frame_target_not_swappable_no_issue() -> None:
    layout = LayoutInfo(
        "root.html", "body", 0, frame_targets=frozenset({"site-header", "site-footer"})
    )
    chain = LayoutChain((layout,))
    reg = _make_registry("main", "page-root")
    issues = check_layout_chains([chain], {"root.html": ""}, fragment_target_registry=reg)
    frame_issues = [i for i in issues if i.category == "layout_frame"]
    assert not frame_issues


def test_frame_target_registered_as_swap_warns() -> None:
    layout = LayoutInfo("root.html", "body", 0, frame_targets=frozenset({"main", "site-footer"}))
    chain = LayoutChain((layout,))
    reg = _make_registry("main", "page-root")
    issues = check_layout_chains([chain], {"root.html": ""}, fragment_target_registry=reg)
    frame_issues = [i for i in issues if i.category == "layout_frame"]
    assert len(frame_issues) == 1
    assert "main" in frame_issues[0].message
    assert "immutable" in frame_issues[0].message


def test_frame_target_check_skipped_without_registry() -> None:
    layout = LayoutInfo("root.html", "body", 0, frame_targets=frozenset({"main"}))
    chain = LayoutChain((layout,))
    issues = check_layout_chains([chain], {"root.html": ""})
    frame_issues = [i for i in issues if i.category == "layout_frame"]
    assert not frame_issues


# --- conflicting outlet_target_id ---


def test_conflicting_outlets_at_same_depth_warns() -> None:
    l1 = LayoutInfo("a.html", "body", 0, outlet_target_id="content-a")
    l2 = LayoutInfo("b.html", "body", 0, outlet_target_id="content-b")
    chain = LayoutChain((l1, l2))
    sources = {
        "a.html": '<div id="content-a"></div>',
        "b.html": '<div id="content-b"></div>',
    }
    issues = check_layout_chains([chain], sources)
    conflict_issues = [i for i in issues if "Conflicting" in i.message]
    assert len(conflict_issues) == 1
    assert "content-a" in conflict_issues[0].message
    assert "content-b" in conflict_issues[0].message


def test_outlets_at_different_depths_no_conflict() -> None:
    l1 = LayoutInfo("root.html", "body", 0, outlet_target_id="site-content")
    l2 = LayoutInfo("section.html", "main", 1, outlet_target_id="section-outlet")
    chain = LayoutChain((l1, l2))
    sources = {
        "root.html": '<div id="site-content"></div>',
        "section.html": '<div id="section-outlet"></div>',
    }
    issues = check_layout_chains([chain], sources)
    conflict_issues = [i for i in issues if "Conflicting" in i.message]
    assert not conflict_issues


def test_same_outlet_at_same_depth_no_conflict() -> None:
    l1 = LayoutInfo("a.html", "body", 0, outlet_target_id="main")
    l2 = LayoutInfo("b.html", "body", 0, outlet_target_id="main")
    chain = LayoutChain((l1, l2))
    sources = {"a.html": '<div id="main"></div>', "b.html": ""}
    issues = check_layout_chains([chain], sources)
    conflict_issues = [i for i in issues if "Conflicting" in i.message]
    assert not conflict_issues
