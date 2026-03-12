"""Unit tests for FragmentTargetRegistry."""

from __future__ import annotations

import pytest

from chirp.http.request import Request
from chirp.templating.composition import PageComposition
from chirp.templating.fragment_target_registry import (
    FragmentTargetConfig,
    FragmentTargetRegistry,
    PageShellContract,
    PageShellTarget,
)
from chirp.templating.render_plan import (
    _fragment_block_for_request,
    _resolve_fragment_block,
    build_render_plan,
)


def test_register_and_get() -> None:
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner")
    reg.register("page-content-inner", fragment_block="page_content")

    cfg = reg.get("page-root")
    assert cfg is not None
    assert cfg.fragment_block == "page_root_inner"

    cfg2 = reg.get("#page-root")
    assert cfg2 is not None
    assert cfg2.fragment_block == "page_root_inner"

    assert reg.get("unknown") is None


def test_is_content_target() -> None:
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner")

    assert reg.is_content_target("page-root") is True
    assert reg.is_content_target("#page-root") is True
    assert reg.is_content_target("other") is False


def test_registered_targets() -> None:
    reg = FragmentTargetRegistry()
    assert reg.registered_targets == frozenset()

    reg.register("page-root", fragment_block="page_root_inner")
    reg.register("page-content-inner", fragment_block="page_content")
    assert reg.registered_targets == frozenset({"page-root", "page-content-inner"})


def test_freeze_prevents_mutation() -> None:
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner")
    reg.freeze()

    with pytest.raises(RuntimeError, match="Cannot modify"):
        reg.register("other", fragment_block="other_block")


def test_fragment_block_for_request_uses_registry() -> None:
    """When registry has target, uses registry's fragment_block."""
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner")
    reg.freeze()

    comp = PageComposition(
        template="test.html",
        fragment_block="page_content",
        page_block="page_root",
        context={},
    )

    class MockRequest:
        is_boosted = True

    from chirp.pages.types import LayoutChain, LayoutInfo

    chain = LayoutChain(
        layouts=(LayoutInfo(template_name="layout.html", target="page-root", depth=1),)
    )

    block = _fragment_block_for_request(
        comp,
        MockRequest(),
        layout_chain=chain,
        layout_start_index=0,
        fragment_target_registry=reg,
    )
    assert block == "page_root_inner"


def test_fragment_block_for_request_fallback_without_registry() -> None:
    """When no registry, uses legacy _CONTENT_ONLY_TARGETS logic."""
    comp = PageComposition(
        template="test.html",
        fragment_block="page_content",
        page_block="page_root",
        context={},
    )

    class MockRequest:
        is_boosted = True

    from chirp.pages.types import LayoutChain, LayoutInfo

    chain = LayoutChain(
        layouts=(LayoutInfo(template_name="layout.html", target="page-root", depth=1),)
    )

    block = _fragment_block_for_request(
        comp,
        MockRequest(),
        layout_chain=chain,
        layout_start_index=0,
        fragment_target_registry=None,
    )
    assert block == "page_content"


def test_resolve_fragment_block_explicit_wins() -> None:
    """Explicit fragment_block always wins over registry."""
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner")
    reg.freeze()

    comp = PageComposition(
        template="test.html",
        fragment_block="custom_block",
        context={},
    )

    class MockRequest:
        htmx_target = "page-root"

    block = _resolve_fragment_block(comp, MockRequest(), fragment_target_registry=reg)
    assert block == "custom_block"


def test_resolve_fragment_block_registry_when_none() -> None:
    """When fragment_block is None, registry lookup via HX-Target is used."""
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner")
    reg.freeze()

    comp = PageComposition(template="test.html", context={})

    class MockRequest:
        htmx_target = "page-root"

    block = _resolve_fragment_block(comp, MockRequest(), fragment_target_registry=reg)
    assert block == "page_root_inner"


def test_resolve_fragment_block_fallback_page_content() -> None:
    """When fragment_block is None and no registry match, fallback to page_content."""
    comp = PageComposition(template="test.html", context={})

    class MockRequest:
        htmx_target = "unknown-target"

    block = _resolve_fragment_block(comp, MockRequest(), fragment_target_registry=None)
    assert block == "page_content"


def test_build_render_plan_local_fragment_uses_registry_when_fragment_block_none() -> None:
    """Local fragment requests (tab clicks) use registry when fragment_block is None."""
    reg = FragmentTargetRegistry()
    reg.register("page-root", fragment_block="page_root_inner")
    reg.freeze()

    comp = PageComposition(template="test.html", context={"x": 1})

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"hx-request", b"true"), (b"hx-target", b"#page-root")],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )

    plan = build_render_plan(
        comp, request=request, fragment_target_registry=reg
    )
    assert plan.intent == "local_fragment"
    assert plan.main_view.block == "page_root_inner"


def test_fragment_target_config_frozen() -> None:
    cfg = FragmentTargetConfig(fragment_block="page_root_inner")
    assert cfg.fragment_block == "page_root_inner"
    with pytest.raises(AttributeError):
        cfg.fragment_block = "other"  # type: ignore[misc]


def test_register_contract_registers_targets_and_required_blocks() -> None:
    reg = FragmentTargetRegistry()
    contract = PageShellContract(
        name="app-shell",
        targets=(
            PageShellTarget(target_id="main", fragment_block="page_root"),
            PageShellTarget(target_id="page-root", fragment_block="page_root_inner"),
            PageShellTarget(
                target_id="page-content-inner",
                fragment_block="page_content",
                triggers_shell_update=False,
            ),
        ),
    )

    reg.register_contract(contract)

    assert reg.registered_targets == frozenset({"main", "page-root", "page-content-inner"})
    assert reg.required_fragment_blocks == frozenset(
        {"page_root", "page_root_inner", "page_content"}
    )
    assert reg.registered_contracts == (contract,)

    cfg = reg.get("page-content-inner")
    assert cfg is not None
    assert cfg.triggers_shell_update is False
    assert cfg.contract_name == "app-shell"
    assert cfg.required is True


def test_register_contract_rejects_multiple_contracts() -> None:
    reg = FragmentTargetRegistry()
    reg.register_contract(
        PageShellContract(
            name="app-shell",
            targets=(PageShellTarget(target_id="main", fragment_block="page_root"),),
        )
    )

    with pytest.raises(ValueError, match="Only one page shell contract"):
        reg.register_contract(
            PageShellContract(
                name="secondary-shell",
                targets=(PageShellTarget(target_id="alt-main", fragment_block="alt_root"),),
            )
        )


def test_fragment_block_for_request_main_target_when_not_in_layout_chain() -> None:
    """When HX-Target is #main (sidebar) and layout chain has page-root, registry resolves main."""
    reg = FragmentTargetRegistry()
    reg.register("main", fragment_block="page_root")
    reg.register("page-root", fragment_block="page_root_inner")
    reg.freeze()

    comp = PageComposition(template="test.html", context={})

    class MockRequest:
        is_boosted = True
        htmx_target = "main"

    from chirp.pages.types import LayoutChain, LayoutInfo

    chain = LayoutChain(
        layouts=(LayoutInfo(template_name="layout.html", target="page-root", depth=1),)
    )

    block = _fragment_block_for_request(
        comp,
        MockRequest(),
        layout_chain=chain,
        layout_start_index=len(chain.layouts),
        fragment_target_registry=reg,
    )
    assert block == "page_root"


def test_build_render_plan_main_target_boosted_returns_page_root() -> None:
    """Boosted sidebar nav (HX-Target #main) returns page_root including tabs."""
    reg = FragmentTargetRegistry()
    reg.register("main", fragment_block="page_root")
    reg.register("page-root", fragment_block="page_root_inner")
    reg.freeze()

    comp = PageComposition(template="workspace/page.html", context={"x": 1})

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/workspace",
            "headers": [
                (b"hx-request", b"true"),
                (b"hx-boosted", b"true"),
                (b"hx-target", b"#main"),
            ],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )

    plan = build_render_plan(
        comp, request=request, fragment_target_registry=reg
    )
    assert plan.intent == "page_fragment"
    assert plan.main_view.block == "page_root"
