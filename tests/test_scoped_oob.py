"""Tests for scoped OOB propagation (Decision 6 of RFC)."""

from __future__ import annotations

from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.server.negotiation_oob import resolve_oob_scope
from chirp.templating.composition import PageComposition
from chirp.templating.fragment_target_registry import (
    FragmentTargetRegistry,
    PageShellContract,
    PageShellTarget,
)
from chirp.templating.render_plan import build_render_plan

# --- scope_name propagation ---


def test_scope_name_on_fragment_target_config() -> None:
    reg = FragmentTargetRegistry()
    reg.register("main", fragment_block="page_root", scope_name="shell")
    reg.freeze()
    cfg = reg.get("main")
    assert cfg is not None
    assert cfg.scope_name == "shell"


def test_scope_name_propagated_from_contract() -> None:
    contract = PageShellContract(
        name="test",
        targets=(
            PageShellTarget(
                target_id="main",
                fragment_block="page_root",
                scope_name="shell",
            ),
            PageShellTarget(
                target_id="page-content-inner",
                fragment_block="page_content",
                triggers_shell_update=False,
                scope_name="content",
            ),
        ),
    )
    reg = FragmentTargetRegistry()
    reg.register_contract(contract)
    reg.freeze()

    assert reg.get("main") is not None
    assert reg.get("main").scope_name == "shell"
    assert reg.get("page-content-inner") is not None
    assert reg.get("page-content-inner").scope_name == "content"


def test_scope_name_default_none() -> None:
    reg = FragmentTargetRegistry()
    reg.register("main", fragment_block="page_root")
    reg.freeze()
    cfg = reg.get("main")
    assert cfg is not None
    assert cfg.scope_name is None


def test_app_register_fragment_target_passes_scope_name() -> None:
    """App.register_fragment_target(scope_name=) must propagate to the registry."""
    from chirp import App, AppConfig

    app = App(AppConfig(template_dir=".", secret_key="test"))
    app.register_fragment_target("site-content", fragment_block="content", scope_name="site")
    reg = app._mutable_state.fragment_target_registry
    cfg = reg.get("site-content")
    assert cfg is not None
    assert cfg.scope_name == "site"


# --- resolve_oob_scope ---


class _FakeRequest:
    def __init__(
        self,
        *,
        is_fragment: bool = True,
        is_boosted: bool = False,
        is_history_restore: bool = False,
        htmx_target: str | None = None,
        path: str = "/",
    ) -> None:
        self.is_fragment = is_fragment
        self.is_boosted = is_boosted
        self.is_history_restore = is_history_restore
        self.htmx_target = htmx_target
        self.path = path


def test_resolve_oob_scope_boosted_returns_none() -> None:
    reg = FragmentTargetRegistry()
    reg.register("main", fragment_block="page_root", scope_name="shell")
    reg.freeze()
    req = _FakeRequest(is_fragment=True, is_boosted=True, htmx_target="main")
    assert resolve_oob_scope(req, reg) is None


def test_resolve_oob_scope_fragment_returns_scope() -> None:
    reg = FragmentTargetRegistry()
    reg.register("page-content-inner", fragment_block="page_content", scope_name="content")
    reg.freeze()
    req = _FakeRequest(is_fragment=True, htmx_target="page-content-inner")
    assert resolve_oob_scope(req, reg) == "content"


def test_resolve_oob_scope_no_target_returns_none() -> None:
    reg = FragmentTargetRegistry()
    reg.freeze()
    req = _FakeRequest(is_fragment=True, htmx_target="unknown")
    assert resolve_oob_scope(req, reg) is None


# --- oob_scope in RenderPlan ---


def test_render_plan_oob_scope_from_target() -> None:
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner", scope_name="page")
    reg.freeze()

    composition = PageComposition(
        template="page.html",
        fragment_block="page_root_inner",
        layout_chain=LayoutChain(
            (
                LayoutInfo("root.html", "body", 0, swap_scope_name="shell"),
                LayoutInfo("section.html", "main", 1, swap_scope_name="page"),
            )
        ),
    )

    req = _FakeRequest(is_fragment=True, htmx_target="page-root")
    plan = build_render_plan(composition, request=req, fragment_target_registry=reg)
    assert plan.oob_scope == "page"


def test_render_plan_oob_scope_none_for_full_page() -> None:
    reg = FragmentTargetRegistry()
    reg.register("main", fragment_block="page_root", scope_name="shell")
    reg.freeze()

    composition = PageComposition(template="page.html", fragment_block="page_root")
    plan = build_render_plan(composition, request=None, fragment_target_registry=reg)
    assert plan.oob_scope is None
