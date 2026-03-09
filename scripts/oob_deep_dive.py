#!/usr/bin/env -S uv run python
"""Deep dive: prefer-regions vs combine for _oob_block_names.

Reproduces the dori layout regression. Run from chirp repo root:
  uv run python scripts/oob_deep_dive.py

Compares:
- prefer_regions: use meta.regions() when available (current fix)
- combine: regions ∪ (blocks ending _oob that aren't regions)
"""

from pathlib import Path

from kida import Environment, FileSystemLoader

from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.composition import PageComposition
from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.render_plan import (
    OOB_BLOCK_SUFFIX,
    CHIRPUI_OOB_BLOCKS,
    build_render_plan,
)

TEMPLATES_DIR = Path(__file__).parent.parent / "tests" / "templates"


def _oob_prefer_regions(adapter, template_name: str) -> set[str]:
    """Current implementation: prefer regions, fallback to blocks."""
    meta = adapter.template_metadata(template_name)
    if meta is None:
        return set()
    regions = getattr(meta, "regions", None)
    if callable(regions):
        region_blocks = regions()
        if region_blocks is not None:
            return {b for b in region_blocks if b.endswith(OOB_BLOCK_SUFFIX)}
    blocks = getattr(meta, "blocks", None)
    if blocks is None:
        return set()
    return {b for b in blocks if b.endswith(OOB_BLOCK_SUFFIX)}


def _oob_combine(adapter, template_name: str) -> set[str]:
    """Combine: regions ∪ (blocks ending _oob that aren't regions)."""
    meta = adapter.template_metadata(template_name)
    if meta is None:
        return set()
    names: set[str] = set()
    regions = getattr(meta, "regions", None)
    if callable(regions):
        region_blocks = regions()
        if region_blocks is not None:
            names = {b for b in region_blocks if b.endswith(OOB_BLOCK_SUFFIX)}
    blocks = getattr(meta, "blocks", None)
    if blocks is not None:
        for name in blocks:
            if name.endswith(OOB_BLOCK_SUFFIX) and name not in names:
                names.add(name)
    return names


def run_composition(
    adapter,
    layout_chain: LayoutChain,
    page_template: str,
    oob_fn,
) -> str:
    """Run full-page composition with given OOB strategy."""
    comp = PageComposition(
        template=page_template,
        fragment_block="content",
        page_block="content",
        context={},
        layout_chain=layout_chain,
    )
    plan = build_render_plan(comp, request=_full_page_request())

    # Override oob collection with our strategy
    oob_blocks_to_suppress = set(CHIRPUI_OOB_BLOCKS)
    for layout_info in plan.layout_chain.layouts[plan.layout_start_index :]:
        oob_blocks_to_suppress |= oob_fn(adapter, layout_info.template_name)

    # Manually run composition with our oob strategy (bypass execute_render_plan)
    main_html = adapter.render_template(plan.main_view.template, plan.main_view.context)
    layouts = plan.layout_chain.layouts[plan.layout_start_index :]

    block_overrides: dict[str, str] = {"content": main_html}
    for name in oob_blocks_to_suppress:
        block_overrides[name] = ""

    for layout_info in reversed(layouts):
        block_overrides["content"] = main_html
        main_html = adapter.compose_layout(
            layout_info.template_name,
            block_overrides,
            plan.layout_context,
        )

    return main_html


def _full_page_request():
    from chirp.http.request import Request

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


def main() -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    adapter = KidaAdapter(env)

    # Case 1: oob_layout (region-based) - both strategies should match
    layout_chain = LayoutChain(
        layouts=(LayoutInfo(template_name="oob_layout/_layout.html", target="body", depth=0),)
    )
    print("=== Case 1: oob_layout (region sidebar_oob) ===\n")

    for name, fn in [("prefer_regions", _oob_prefer_regions), ("combine", _oob_combine)]:
        oob = fn(adapter, "oob_layout/_layout.html")
        print(f"  {name}: {sorted(oob)}")

    pref = run_composition(adapter, layout_chain, "oob_layout/page.html", _oob_prefer_regions)
    comb = run_composition(adapter, layout_chain, "oob_layout/page.html", _oob_combine)

    print("\n  prefer_regions output (snippet):", pref[200:400] if len(pref) > 400 else pref)
    print("  combine output (snippet):       ", comb[200:400] if len(comb) > 400 else comb)
    print("  Same?", pref == comb)
    print("  Card intact (prefer)?", "card__header" in pref and "card__body" in pref)
    print("  Card intact (combine)?", "card__header" in comb and "card__body" in comb)

    # Case 2: block_oob_layout (regular block named content_oob) - combine may break
    print("\n=== Case 2: block_oob_layout (regular block content_oob) ===\n")
    block_oob_layout = TEMPLATES_DIR / "oob_layout" / "block_oob_layout.html"
    if block_oob_layout.exists():
        for name, fn in [("prefer_regions", _oob_prefer_regions), ("combine", _oob_combine)]:
            oob = fn(adapter, "oob_layout/block_oob_layout.html")
            print(f"  {name}: {sorted(oob)}")

        chain2 = LayoutChain(
            layouts=(
                LayoutInfo(
                    template_name="oob_layout/block_oob_layout.html", target="body", depth=0
                ),
            )
        )
        pref2 = run_composition(
            adapter, chain2, "oob_layout/block_oob_page.html", _oob_prefer_regions
        )
        comb2 = run_composition(adapter, chain2, "oob_layout/block_oob_page.html", _oob_combine)
        # combine suppresses content_oob (regular block) in outer layout; prefer does not
        outer_has_critical_prefer = pref2.count("CRITICAL_STRUCTURE") >= 1
        outer_has_critical_combine = (
            "critical-wrapper" in comb2.split("<main")[0]
        )  # before first <main>
        print("  Same?", pref2 == comb2)
        print("  Outer layout has critical-wrapper (prefer)?", outer_has_critical_prefer)
        print("  Outer layout has critical-wrapper (combine)?", outer_has_critical_combine)
    else:
        print("  (block_oob_layout.html not found - create to test combine breakage)")


if __name__ == "__main__":
    main()
