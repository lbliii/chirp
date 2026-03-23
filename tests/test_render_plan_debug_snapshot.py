"""Tests for render plan snapshot on the debug error page."""

from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.server.debug.render_plan_snapshot import (
    RENDER_DEBUG_CACHE_KEY,
    read_render_debug_from_request,
    serialize_render_plan_for_debug,
    stash_render_debug_for_request,
    summarize_context_for_debug,
)
from chirp.server.debug_page import render_debug_page
from chirp.templating.composition import PageComposition, RegionUpdate, ViewRef
from chirp.templating.render_plan import RenderPlan, build_render_plan


def _minimal_plan() -> RenderPlan:
    chain = LayoutChain(
        layouts=(
            LayoutInfo(template_name="root.html", target="body", depth=0),
            LayoutInfo(template_name="shell.html", target="app-content", depth=1),
        )
    )
    composition = PageComposition(
        template="page.html",
        fragment_block="content",
        page_block="content",
        context={"title": "Hi", "n": 42},
        layout_chain=chain,
    )
    return build_render_plan(composition, request=None)


def test_summarize_context_for_debug_truncates_long_repr() -> None:
    long_val = "x" * 200
    rows = summarize_context_for_debug({"k": long_val})
    assert len(rows) == 1
    assert len(rows[0][1]) <= 123  # 120 + "..."
    assert rows[0][1].endswith("...")


def test_summarize_context_for_debug_caps_keys() -> None:
    ctx = {str(i): i for i in range(60)}
    rows = summarize_context_for_debug(ctx)
    assert any(r[0] == "…" for r in rows)


def test_serialize_render_plan_for_debug_shape() -> None:
    plan = _minimal_plan()
    snap = serialize_render_plan_for_debug(plan)
    assert snap["intent"] in ("full_page", "page_fragment", "local_fragment")
    assert "main_view" in snap
    assert snap["main_view"]["template"] == "page.html"
    assert "title" in snap["main_view"]["context_keys"]
    assert len(snap["layout_chain"]) == 2
    assert snap["layout_chain"][0]["target"] == "body"


def test_stash_and_read_roundtrip() -> None:
    plan = _minimal_plan()

    class R:
        _cache: dict[str, object]

    r = R()
    r._cache = {}
    stash_render_debug_for_request(plan, r, debug=True)  # type: ignore[arg-type]
    got = read_render_debug_from_request(r)
    assert got is not None
    assert got["main_view"]["template"] == "page.html"


def test_render_debug_page_includes_render_plan_panel() -> None:
    plan = RenderPlan(
        intent="full_page",
        main_view=ViewRef(template="x.html", block="main", context={"a": 1}),
        render_full_template=False,
        apply_layouts=True,
        layout_chain=LayoutChain(
            layouts=(LayoutInfo(template_name="L.html", target="body", depth=0),)
        ),
        layout_start_index=0,
        layout_context={"current_path": "/"},
        region_updates=(
            RegionUpdate(
                region="sidebar",
                view=ViewRef(template="part.html", block="nav", context={}),
            ),
        ),
        include_layout_oob=False,
    )
    snap = serialize_render_plan_for_debug(plan)

    class FakeReq:
        pass

    req = FakeReq()
    req._cache = {RENDER_DEBUG_CACHE_KEY: snap}  # type: ignore[attr-defined]

    html = render_debug_page(RuntimeError("fail"), req)
    assert "<h2>Render plan</h2>" in html
    assert "x.html" in html
    assert "Layout chain" in html
    assert "L.html" in html
    assert "sidebar" in html
    assert "Main context" in html
