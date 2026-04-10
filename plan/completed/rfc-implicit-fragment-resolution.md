# RFC: Implicit Fragment Resolution — Eliminate Per-Page fragment_block

**Status**: Implemented
**Date**: 2026-03-11
**Scope**: `PageComposition`, `FragmentTargetRegistry`, `render_plan`, `upgrade_result`
**Related**: OOB Registry (oob-registry branch), dori dashboard route tabs, chirp-ui app shell

## Implementation Notes (2026-03-11)

- **`main` target**: ChirpUI registers `main` → `page_root` for sidebar links (`hx-target="#main"`). Without this, boosted sidebar navigation returned `page_content` (no tabs) because `#main` is not in the layout chain.
- **Target-not-in-layout-chain**: When `HX-Target` does not match any layout target, `_fragment_block_for_request` now consults the registry via `_resolve_fragment_block` instead of blindly returning `page_content`.
- **Full-page fallback**: Default block for full-page loads when both `page_block` and `fragment_block` are `None` is `page_root` (not `page_content`) so tabs render on initial load.
- **Unregistered target logging**: When a request has `HX-Target` and a registry exists but the target is unregistered, Chirp logs at debug level to aid troubleshooting.
- **Shell actions configurable**: `FragmentTargetConfig` now has `triggers_shell_update` (default True). When a target has this flag, swapping it triggers shell_actions OOB. ChirpUI sets `triggers_shell_update=False` for `page-content-inner` so narrow swaps don't update the topbar. Apps can configure via `app.register_fragment_target(..., triggers_shell_update=False)`.

---

## Problem

Every page handler that returns `PageComposition` must specify a `fragment_block` — the template block rendered for non-boosted HTMX fragment requests (tab clicks, inline updates). This value is determined by the page's template structure, not by the page's domain logic, yet it lives in the handler.

This is a proven footgun. In the dori dashboard, 11 out of 22 tabbed pages had `fragment_block="page_content"` when they needed `"page_root_inner"`. The result: clicking a tab wiped out the tab navigation bar, because the rendered fragment was too narrow to include the tabs.

The pages that worked (Discover section) had:

```python
# shortcuts/page.py — works
PageComposition(
    template="shortcuts/page.html",
    fragment_block="page_root_inner",   # includes tabs
    page_block="page_root",
    context={...},
)
```

The pages that broke (Workspace, Workflows, Operations) had:

```python
# workspace/analytics/page.py — tabs disappear on click
PageComposition(
    template="workspace/analytics/page.html",
    fragment_block="page_content",       # too narrow, excludes tabs
    page_block="page_root",
    context={...},
)
```

The correct value depends on the template's block hierarchy — specifically whether the `hx-target` element contains section-level chrome (tabs, toolbars, filters) above the page content. This is structural knowledge that belongs to the template, not to 22 individual page handlers.

---

## Current State

### `PageComposition` requires `fragment_block`

`fragment_block` is a required positional field:

```python
# src/chirp/templating/composition.py:43-78
@dataclass(frozen=True, slots=True)
class PageComposition:
    template: str
    fragment_block: str              # required — the footgun
    page_block: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    regions: tuple[RegionUpdate, ...] = ()
    layout_chain: LayoutChain | None = None
    context_providers: tuple[ContextProvider, ...] = ()
```

### `FragmentTargetRegistry` exists but is under-consulted

Chirp already has an app-level registry mapping HTMX target IDs to fragment blocks:

```python
# src/chirp/templating/fragment_target_registry.py
class FragmentTargetRegistry:
    def register(self, target_id: str, *, fragment_block: str) -> None: ...
    def get(self, target_id: str) -> FragmentTargetConfig | None: ...
```

ChirpUI registers the standard targets during `use_chirp_ui()`:

```python
# src/chirp/ext/chirp_ui.py:98-99
app.register_fragment_target("page-root", fragment_block="page_root_inner")
app.register_fragment_target(
    "page-content-inner",
    fragment_block="page_content",
    triggers_shell_update=False,
)
```

The lifecycle is complete: created in `MutableAppState`, registered during setup, frozen in `AppCompiler.freeze()`, threaded through `runtime → handler → negotiation → build_render_plan`.

### The gap: registry ignored for local fragments

In `build_render_plan()`, the render intent is determined by request type:

```python
# src/chirp/templating/render_plan.py:169-193
if not _should_render_page_block(request):
    intent = "local_fragment"
    block = composition.fragment_block        # <-- DIRECT, no registry
    apply_layouts = False
elif is_fragment and not is_history_restore:
    intent = "page_fragment"
    block = _fragment_block_for_request(...)   # <-- CONSULTS REGISTRY
else:
    intent = "full_page"
    block = composition.page_block or composition.fragment_block
```

For **boosted navigation** (sidebar clicks with `HX-Boosted: true`), `_fragment_block_for_request()` consults the `FragmentTargetRegistry`. For **local fragment requests** (tab clicks, form submits — `HX-Request: true` without `HX-Boosted`), the registry is never consulted. The page's `fragment_block` is used directly.

Tab links send:

```html
<a hx-get="/workspace/analytics"
   hx-target="#page-root"
   hx-push-url="true"
   hx-swap="innerHTML">Analytics</a>
```

This has `HX-Request: true` and `HX-Target: #page-root`, but NOT `HX-Boosted: true`. The registry already knows that `page-root → page_root_inner`. But `build_render_plan()` ignores it and uses `composition.fragment_block` — which, if wrong, breaks the UI silently.

### `template_name` not threaded to `upgrade_result`

During `mount_pages()` discovery, each `PageRoute` carries a `template_name` (from the sibling `.html` file convention). However, `register_page_handler()` does not pass `template_name` into the `page_wrapper` closure:

```python
# src/chirp/app/registry.py:168-174
async def page_wrapper(request: Request) -> Any:
    cascade_ctx = await build_cascade_context(...)
    kwargs = await resolve_kwargs(_handler, request, cascade_ctx, _service_providers)
    result = await invoke(_handler, **kwargs)
    return upgrade_result(result, cascade_ctx, _chain, _providers, request=request)
```

This means `upgrade_result()` cannot infer `template` for handlers that return plain dicts.

### Dict returns become JSON

Handlers that return dicts are currently serialized as JSON responses by `negotiate()`:

```python
# src/chirp/server/negotiation.py
case dict() | list():
    return JSONResponse.from_value(value)
```

There is no path from dict → `PageComposition` → template render.

---

## Goals

1. Pages should not need to specify `fragment_block` for the common case.
2. The `FragmentTargetRegistry` should resolve fragments for ALL request types, not just boosted.
3. Page handlers should be able to return plain dicts and get template rendering (not JSON) when a sibling template exists.
4. The 11-file class of footgun (wrong `fragment_block` silently breaks UI) should become impossible.

### Non-Goals

- Adding a `SectionDefaults`, `RouteTab`, or other section-level abstraction to the framework. Navigation shapes (tabs, steppers, filter bars) are template context, not framework primitives.
- Changing template syntax or adding new template annotations.
- Removing `fragment_block` from `PageComposition`. Explicit override must remain available for pages that need non-standard behavior.

---

## Decision

Three surgical changes to existing infrastructure. No new abstractions.

### 1. Make `fragment_block` optional on `PageComposition`

```python
# src/chirp/templating/composition.py — proposed
@dataclass(frozen=True, slots=True)
class PageComposition:
    template: str
    fragment_block: str | None = None   # was: str (required)
    page_block: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    regions: tuple[RegionUpdate, ...] = ()
    layout_chain: LayoutChain | None = None
    context_providers: tuple[ContextProvider, ...] = ()
```

When `fragment_block` is `None`, the render plan resolves it from the `FragmentTargetRegistry` using the request's `HX-Target` header. When explicitly set, the explicit value wins (escape hatch preserved).

### 2. Consult `FragmentTargetRegistry` for local fragments

Extend `build_render_plan()` to check the registry when `fragment_block` is `None` or when the request carries an `HX-Target`:

```python
# src/chirp/templating/render_plan.py — proposed
if not _should_render_page_block(request):
    intent = "local_fragment"
    block = _resolve_fragment_block(
        composition, request, fragment_target_registry
    )
    apply_layouts = False
```

Where `_resolve_fragment_block` is:

```python
def _resolve_fragment_block(
    composition: PageComposition,
    request: Request | None,
    registry: FragmentTargetRegistry | None,
) -> str:
    """Resolve fragment block: explicit > registry > fallback."""
    # Explicit override always wins
    if composition.fragment_block is not None:
        return composition.fragment_block
    # Consult registry via HX-Target
    if request and request.htmx_target and registry:
        config = registry.get(request.htmx_target)
        if config:
            return config.fragment_block
    # Fallback: page_block or convention
    return composition.page_block or "page_content"
```

Resolution order: **explicit `fragment_block`** > **registry lookup via `HX-Target`** > **`page_block`** > **`"page_content"` default**.

### 3. Support dict returns as rendered pages

Thread `template_name` through the handler wrapper and add dict handling to `upgrade_result()`:

```python
# src/chirp/app/registry.py — proposed change to register_page_handler
_template = template_name   # close over template_name from PageRoute

async def page_wrapper(request: Request) -> Any:
    cascade_ctx = await build_cascade_context(...)
    kwargs = await resolve_kwargs(_handler, request, cascade_ctx, _service_providers)
    result = await invoke(_handler, **kwargs)
    return upgrade_result(
        result, cascade_ctx, _chain, _providers,
        request=request, template_name=_template,
    )
```

```python
# src/chirp/pages/resolve.py — proposed addition to upgrade_result
if isinstance(result, dict) and template_name is not None:
    merged_ctx = _merge_result_context(cascade_ctx, result)
    return PageComposition(
        template=template_name,
        context=merged_ctx,
        layout_chain=layout_chain,
        context_providers=context_providers,
    )
```

When a handler returns a dict AND a sibling template exists, the dict becomes `PageComposition.context` and the template is rendered. `fragment_block` and `page_block` are `None` — resolved from the registry at render time.

When no sibling template exists, dicts continue to serialize as JSON (existing behavior, handled by `negotiate()`).

---

## What Changes for App Developers

### Before (current — 11 lines, footgun-prone)

```python
# workspace/analytics/page.py
def get(request, orchestrator):
    return PageComposition(
        template="workspace/analytics/page.html",
        fragment_block="page_root_inner",   # must match template structure
        page_block="page_root",             # same for every tabbed page
        context={
            "current_path": request.path,
            "page_title": "Analytics",
            "route_tabs": WORKSPACE_TABS,
            "breadcrumb_items": [{"label": "Home", "href": "/"}, {"label": "Workspace"}],
            "summary": orchestrator.get_summary(),
        },
    )
```

### After (proposed — 3 lines for the handler)

With `_context.py` providing shared context (existing feature):

```python
# workspace/_context.py
from myapp.tabs import WORKSPACE_TABS

def context(request):
    return {
        "current_path": request.path,
        "route_tabs": WORKSPACE_TABS,
        "breadcrumb_items": [
            {"label": "Home", "href": "/"},
            {"label": "Workspace"},
        ],
    }
```

```python
# workspace/analytics/page.py — pure domain logic
def get(orchestrator):
    return {"page_title": "Analytics", "summary": orchestrator.get_summary()}
```

No `fragment_block`, no `page_block`, no `template` path. The framework resolves all three from existing infrastructure: sibling template convention, `FragmentTargetRegistry`, and layout chain.

For pages that need explicit control, `PageComposition` with explicit `fragment_block` still works:

```python
# special/page.py — explicit override
def get():
    return PageComposition(
        template="special/page.html",
        fragment_block="custom_block",
        context={"special": True},
    )
```

---

## Implementation Plan

### Phase 1: Make `fragment_block` optional (non-breaking)

1. Change `PageComposition.fragment_block` from `str` to `str | None = None`.
2. Update `build_render_plan()` to call `_resolve_fragment_block()` for local fragments.
3. Update `_fragment_block_for_request()` to handle `None` by consulting the registry.
4. All existing code continues to work — every current `PageComposition` explicitly sets `fragment_block`.

**Files changed:**
- `src/chirp/templating/composition.py`
- `src/chirp/templating/render_plan.py`

### Phase 2: Thread `template_name` and support dict returns

1. Pass `template_name` from `PageRoute` through `register_page_handler()` into the `page_wrapper` closure.
2. Add `template_name: str | None = None` parameter to `upgrade_result()`.
3. Add `isinstance(result, dict)` handling that wraps into `PageComposition`.
4. `negotiate()` dict handling unchanged — dict-from-non-page-routes still becomes JSON.

**Files changed:**
- `src/chirp/app/registry.py`
- `src/chirp/pages/resolve.py`

### Phase 3: Migrate dori dashboard (validation)

1. Remove explicit `fragment_block` and `page_block` from all 22+ page handlers.
2. Move repeated context (route_tabs, breadcrumb_prefix) into `_context.py` per section.
3. Convert handlers to return dicts.
4. Verify all dashboard tests pass.

**Files changed:** `src/dori/dashboard/pages/*/page.py`, `src/dori/dashboard/pages/*/_context.py`

---

## Alternatives Considered

### A. `SectionDefaults` dataclass

A new `SectionDefaults` concept in `_context.py` providing `route_tabs`, `fragment_block`, `breadcrumb_prefix` per directory.

Rejected because:
- Introduces a new framework abstraction when existing primitives suffice.
- `route_tabs` is a template-level concern (tabs are just one navigation shape); the framework should not have opinions about navigation shapes.
- `fragment_block` is a structural concern (template block hierarchy), not a section concern.

### B. Template annotations (`{# fragment: page_root_inner #}`)

Templates declare their fragment boundary via comments, parsed at discovery time.

Rejected because:
- Requires parsing `{% extends %}` chains to find the annotation.
- The `FragmentTargetRegistry` already expresses the same relationship (target ID → block) without template parsing.
- The HTMX `hx-target` attribute on the triggering element already carries the structural intent.

### C. Per-directory `_section.py` file

A new discovery file that provides section-level composition defaults.

Rejected because:
- Adds a new file convention alongside `_context.py` and `_layout.html`.
- The `_context.py` `context()` function already provides shared template data.
- The `FragmentTargetRegistry` already handles composition defaults.
- More concepts to learn with no additional capability.

---

## Open Questions

1. **Fallback when `fragment_block` is `None` and no `HX-Target` in request.** This happens during testing or server-side rendering without HTMX. The proposed fallback chain is `page_block → "page_content"`. Is `"page_content"` the right universal default, or should it be configurable?

2. **Dict return priority vs JSON.** When a page handler returns a dict and has a sibling template, the proposed behavior is to render the template (not return JSON). Should this be opt-in (e.g., a decorator or convention like `page.html` presence) or always-on? The current proposal uses sibling template existence as the signal.

3. **`normalize_to_composition` compatibility.** The `normalize_to_composition()` function in `render_plan.py` converts `Page`/`LayoutPage` to `PageComposition`. It currently requires `fragment_block`. This needs updating to allow `None`. Should `Page` and `LayoutPage` also get optional `block_name`?

4. **Backward compatibility for `PageComposition(template, fragment_block, ...)`** positional usage. Making `fragment_block` optional changes its position. Existing code using positional args (`PageComposition("foo.html", "page_content", ...)`) will break. Migration path: keyword-only enforcement or deprecation period?

---

## Validation

Success looks like:

- `fragment_block` on `PageComposition` defaults to `None` with no test regressions.
- The `FragmentTargetRegistry` resolves the correct block for tab clicks (local fragments), not just boosted navigation.
- Dori dashboard page handlers are 3-5 line functions returning dicts, with no `fragment_block` or `page_block`.
- The 11-file footgun class is eliminated — new pages cannot get the wrong fragment block unless they explicitly override.
- Existing apps that set `fragment_block` explicitly continue to work unchanged.
- Navigation shapes (tabs, steppers, filters) remain template context — the framework has no opinion on the shape.

---

## References

- `src/chirp/templating/composition.py` — `PageComposition` definition
- `src/chirp/templating/render_plan.py` — `build_render_plan()`, `_fragment_block_for_request()`
- `src/chirp/templating/fragment_target_registry.py` — `FragmentTargetRegistry`
- `src/chirp/ext/chirp_ui.py` — ChirpUI target registration
- `src/chirp/pages/resolve.py` — `upgrade_result()`
- `src/chirp/pages/discovery.py` — `_walk_directory()`, `_load_context_provider()`
- `src/chirp/app/registry.py` — `register_page_handler()`, `page_wrapper`
- dori `src/dori/dashboard/pages/workspace/*/page.py` — the 11 pages with wrong `fragment_block`
