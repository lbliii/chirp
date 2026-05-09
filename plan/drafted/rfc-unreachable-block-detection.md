# RFC: Unreachable Block Detection in Page Templates

**Status**: Implemented  
**Updated**: 2026-05-09 - `rules_unreachable_blocks.py`, checker wiring, contract tests, and fragment-block regression coverage exist. Remaining follow-up is app.check integration proof through real page/layout discovery plus a documented empty-block noise policy.  
**Date**: 2026-04-11  
**Scope**: `src/chirp/contracts/rules_unreachable_blocks.py`, `src/chirp/contracts/checker.py`  
**Related**: RFC: Contract Validation Extensions (`plan/drafted/rfc-contract-extensions.md`), RFC: Hierarchical Shell Swap Scopes

---

## Problem

When a filesystem page template defines `{% block page_scripts %}...{% end %}`, Chirp's layout composition pipeline silently drops it. The content vanishes without any error, warning, or runtime indication.

This happens because Chirp's composition model uses `render_with_blocks` — not template inheritance. The layout chain renderer (`src/chirp/pages/renderer.py:70-73`) passes only `{"content": html}` into each layout:

```python
html = page_html
for layout_info in reversed(layouts_to_render):
    template = env.get_template(layout_info.template_name)
    html = template.render_with_blocks({"content": html}, **context)
```

The page template is rendered via `render_block("page_root", ...)` or `render_block("page_content", ...)`. Only blocks that are children of the rendered block are included in the output. Blocks defined as siblings — like `page_scripts` in `app_shell_layout.html` — are never reached because the page template does not `{% extends %}` the layout. The layout renders its own `page_scripts` block from its own source; the page template's version has no way to participate.

### Evidence

This was discovered during the b-site matching game implementation. A page template at `pages/play/page.html` defined:

```kida
{% block page_root %}
  <div id="page-root">
    {% block page_content %}
      <!-- game board -->
    {% end %}
  </div>
{% end %}

{% block page_scripts %}
<script>
  // Alpine component registration — 150+ lines
  Alpine.data("matchGame", function() { ... });
</script>
{% end %}
```

The `page_scripts` block was silently ignored. The game loaded with no JavaScript — no error in the server log, no template error, no contract check failure. Diagnosis required browser DevTools inspection to realize the script tag was simply absent from the HTML.

### Why This Is a Sharp Edge

1. **Silent failure** — The page renders successfully (200 OK). The missing content is only detectable by manual inspection.
2. **Jinja2 muscle memory** — In Jinja2 with `{% extends %}`, sibling blocks are a standard pattern. Developers (and AI agents) naturally reach for this.
3. **`page_scripts` exists in the layout** — `app_shell_layout.html` defines `{% block page_scripts %}{% end %}` as an extension point, creating the expectation that page templates can fill it.
4. **Existing checks don't catch it** — `check_page_shell_contracts` validates that required blocks *exist* in the page template, but does not check for blocks that exist in the page but are *not reachable* through composition.

### Data Already Available

`ContractCheckSnapshot` (`src/chirp/app/state.py:102-127`) provides everything needed:

- `page_leaf_templates: set[str]` — leaf page template names
- `layout_chains: list[Any]` — layout chain metadata per route
- `kida_env: Environment` — for `block_metadata()` and `template_metadata()`
- `template_sources: dict[str, str]` — raw template sources

---

## Goals

1. Detect page-defined blocks that are unreachable through `render_with_blocks` composition.
2. Emit a clear WARNING with actionable guidance ("put this inside `page_content`").
3. Zero false positives for blocks that *are* reachable (children of `content`, `page_root`, `page_content`).
4. Fit naturally into the existing contract checker pipeline.

### Non-Goals

- Changing the composition model to support multi-block injection (that's a separate, larger design question).
- Detecting unreachable content that isn't in a named block (e.g. bare HTML after `{% end %}` of `page_root`).
- Runtime detection — this is compile-time / startup only.

---

## Design

### New Rule Module: `rules_unreachable_blocks.py`

```python
"""Unreachable block detection for filesystem page templates."""

from typing import Any

from kida import Environment

from .types import ContractIssue, Severity


def check_unreachable_blocks(
    page_leaf_templates: set[str],
    layout_chains: list[Any],
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Detect blocks in page templates that render_with_blocks cannot reach.

    When Chirp composes filesystem pages into layouts, only the ``content``
    block (and its children) are injected.  Blocks defined as siblings of
    ``content`` in the page template are silently ignored.  This check
    identifies those blocks and warns the author.
    """
    issues: list[ContractIssue] = []
    if not page_leaf_templates or kida_env is None:
        return issues

    # Collect layout block names across all layout templates in all chains
    layout_block_names: set[str] = set()
    for chain in layout_chains:
        for layout in getattr(chain, "layouts", ()):
            try:
                tmpl = kida_env.get_template(layout.template_name)
                layout_block_names.update(tmpl.block_metadata())
            except Exception:
                continue

    # The composition slot — always reachable
    COMPOSITION_ROOTS = {"content", "page_root", "page_content"}

    for template_name in sorted(page_leaf_templates):
        try:
            template = kida_env.get_template(template_name)
            page_blocks = template.block_metadata()
        except Exception:
            continue

        # Reachable: blocks that are children of composition roots,
        # OR blocks that are composition roots themselves
        reachable = _collect_reachable_blocks(page_blocks, COMPOSITION_ROOTS)

        for block_name in sorted(page_blocks):
            if block_name in reachable:
                continue
            # Block exists in page but is not reachable through composition
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="unreachable_block",
                    message=(
                        f"Page template '{template_name}' defines block "
                        f"'{block_name}' but it is not reachable via "
                        "render_with_blocks — this block will be silently "
                        "ignored. Place content inside 'page_content' or "
                        "'page_root' instead."
                    ),
                    template=template_name,
                    details=(
                        "Chirp's filesystem page composition injects only the "
                        "'content' block (and its children) into layouts. "
                        "Sibling blocks like 'page_scripts' are not inherited "
                        "— unlike {% extends %}, render_with_blocks does not "
                        "merge all blocks."
                    ),
                )
            )

    return issues


def _collect_reachable_blocks(
    page_blocks: dict[str, Any],
    roots: set[str],
) -> set[str]:
    """Walk block metadata to find all blocks nested under composition roots."""
    reachable: set[str] = set()
    for name in page_blocks:
        if name in roots:
            reachable.add(name)
            # Add all children (blocks nested inside this one)
            _add_children(page_blocks, name, reachable)
    return reachable


def _add_children(
    blocks: dict[str, Any],
    parent: str,
    reachable: set[str],
) -> None:
    """Recursively add child blocks of a parent block."""
    meta = blocks.get(parent)
    if meta is None:
        return
    children = getattr(meta, "children", None) or ()
    for child_name in children:
        if child_name not in reachable:
            reachable.add(child_name)
            _add_children(blocks, child_name, reachable)
```

### Algorithm

1. Collect all block names across all layout templates in all discovered layout chains.
2. For each page leaf template, call `template.block_metadata()` to get all blocks defined in the page.
3. Starting from known composition roots (`content`, `page_root`, `page_content`), walk the block tree to collect all reachable blocks (roots + their children at any depth).
4. Any page-defined block NOT in the reachable set is unreachable — emit a WARNING.

### Block Metadata API

Kida's `block_metadata()` returns `dict[str, BlockMetadata]`. Each `BlockMetadata` includes:
- `name` — block name
- `children` — names of blocks nested inside this block
- `depends_on` — context variables referenced
- `cache_scope` — site/page/none
- `is_pure` — whether the block is side-effect-free

The `children` field is the key enabler: it lets us walk from `page_root` → `page_content` → any deeper blocks and confirm they are reachable.

### Integration into checker.py

Add to `check_hypermedia_surface()` at line ~376 (after `check_page_shell_contracts`):

```python
from .rules_unreachable_blocks import check_unreachable_blocks

# After check_page_shell_contracts:
result.issues.extend(
    check_unreachable_blocks(
        snapshot.page_leaf_templates,
        snapshot.layout_chains,
        kida_env,
    )
)
```

### Output Example

```
WARNING [unreachable_block] Page template 'play/page.html' defines block
  'page_scripts' but it is not reachable via render_with_blocks — this
  block will be silently ignored. Place content inside 'page_content'
  or 'page_root' instead.
           Chirp's filesystem page composition injects only the 'content'
           block (and its children) into layouts. Sibling blocks like
           'page_scripts' are not inherited — unlike {% extends %},
           render_with_blocks does not merge all blocks.
```

### Severity

**WARNING** — The page still renders (200 OK), but content is missing. This is not an ERROR because:
- The app is functional (no crash)
- The missing content may be intentional during development
- Severity can be promoted to ERROR via `app.override_contract_severity("unreachable_block", Severity.ERROR)`

---

## Edge Cases

### Blocks defined in both page and layout

If the page defines `page_scripts` and the layout also defines `page_scripts`, the page's version is still unreachable through `render_with_blocks`. The layout renders its own definition. This should still be flagged.

### Pages that use `{% extends %}` instead of composition

If a page template uses `{% extends "base.html" %}`, it participates in Kida's native inheritance — all blocks in the inheritance chain are reachable. The check should skip templates that use `{% extends %}` (they are not rendered via `render_with_blocks`).

Detection: check `template.template_metadata().extends` — if non-None, skip the template.

### Empty blocks

`{% block extra_head %}{% end %}` in a page template is technically unreachable if it's a sibling of `content`, but it's also empty and harmless. Consider suppressing warnings for empty unreachable blocks to reduce noise.

### Custom composition roots

Some apps may pass additional blocks to `render_with_blocks` beyond `content`. The check should allow configuration via `app.set_contract_check_data("composition_roots", {"content", "sidebar"})` so apps with custom composition can suppress false positives.

---

## Testing Strategy

1. **Basic case**: Page defines `page_scripts` as a sibling of `page_root` → WARNING emitted.
2. **Nested blocks**: Page defines `page_root` → `page_content` → `inner_block` → no warning for any of these.
3. **Empty unreachable block**: Page defines empty `{% block extra %}{% end %}` outside `content` → WARNING (or suppressed, TBD).
4. **Extends template**: Page uses `{% extends "base.html" %}` → skip (no warning).
5. **No page templates**: App has no `mount_pages` → empty result.
6. **Custom composition roots**: App sets extra roots via `set_contract_check_data` → those blocks are not flagged.

---

## Relationship to Existing RFCs

This is a natural **Extension 5** to `rfc-contract-extensions.md`, which already covers dead templates, form fields, component calls, and SSE fragments. The pattern is identical: use startup-time introspection to catch a class of bugs that currently requires manual testing.

It also relates to `rfc-hierarchical-shell-swap-scopes.md` — as the swap scope model evolves, the set of "reachable blocks" may expand. The `composition_roots` configuration mechanism provides forward compatibility.
