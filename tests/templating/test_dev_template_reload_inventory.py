"""Lifecycle contract proof for the internal template reload planner."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Page
from chirp.templating.dev_template_reload import (
    TemplateReloadPlanner,
    TemplateReloadSurface,
    build_template_reload_inventory,
)

pytestmark = pytest.mark.issue(341)


def _write_nested_page(path: Path, content: str) -> None:
    path.write_text(
        "{% block page_root %}"
        '<div id="page-root">'
        "{% block page_content %}"
        f'<main id="main">{content}</main>'
        "{% end %}"
        "</div>"
        "{% end %}",
        encoding="utf-8",
    )


def test_frozen_app_inventory_uses_route_and_fragment_registration(tmp_path: Path) -> None:
    template = tmp_path / "page.html"
    _write_nested_page(template, "before")
    app = App(AppConfig(debug=True, template_dir=tmp_path))
    app.register_fragment_target("main", fragment_block="page_content")

    @app.route("/", template="page.html")
    def index() -> Page:
        return Page("page.html", "page_content", page_block_name="page_root")

    app.freeze()
    inventory = build_template_reload_inventory(
        app._runtime_state.kida_env,
        app._runtime_state.hypermedia_program,
        app._runtime_state.fragment_target_registry,
    )

    assert len(inventory.entries) == 1
    entry = inventory.entries[0]
    assert entry.template_name == "page.html"
    assert entry.route_paths == ("/",)
    assert [(target.target_id, target.block_name) for target in entry.targets] == [
        ("main", "page_content")
    ]


def test_nested_page_edit_keeps_full_reload_when_ancestor_hashes_also_change(
    tmp_path: Path,
) -> None:
    template = tmp_path / "page.html"
    _write_nested_page(template, "before")
    app = App(AppConfig(debug=True, template_dir=tmp_path))
    app.register_fragment_target("main", fragment_block="page_content")

    @app.route("/", template="page.html")
    def index() -> Page:
        return Page("page.html", "page_content", page_block_name="page_root")

    app.freeze()
    env = app._runtime_state.kida_env
    assert env is not None
    planner = TemplateReloadPlanner(
        env,
        build_template_reload_inventory(
            env,
            app._runtime_state.hypermedia_program,
            app._runtime_state.fragment_target_registry,
        ),
    )
    _write_nested_page(template, "after")
    surface = TemplateReloadSurface(
        reachable_templates=frozenset({"page.html"}),
        route_target_ids=frozenset({"main"}),
        live_target_counts=(("main", 1),),
        get_safe=True,
        htmx_adapter_available=True,
    )

    plan = planner.plan_edit(template, surface)

    assert plan.outcome == "reload"
    assert plan.reason == "multiple_blocks_changed"
    assert plan.changed_blocks == ("page_content", "page_root")
    assert plan.target_id is None
