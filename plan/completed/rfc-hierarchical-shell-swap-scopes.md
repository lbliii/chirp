# RFC: Hierarchical Shell Swap Scopes — Nested Layouts as a First-Class Contract

**Status**: Implemented  
**Date**: 2026-04-11  
**Scope**: `LayoutInfo`, `LayoutChain`, `FragmentTargetRegistry`, `PageShellContract`, `LayoutContract`, `OOBBlockInfo`, `build_render_plan`, shell negotiation (`negotiation_oob`), chirp-ui integration, filesystem layouts  
**Related**: RFC: Implicit Fragment Resolution, RFC: Route Directory Contract, [UI layers & shell regions](/site/content/docs/guides/ui-layers.md)

---

## Problem

Chirp already models **nested layouts** (`_layout.html` chains) and **fragment targets** (`FragmentTargetRegistry`), and the render plan already uses `HX-Target` to pick a **layout start index** and resolve **which Kida block** to render. That is enough for a single app shell plus a tabbed page.

It is **not** yet a complete *mental model or contract surface* for apps that stack shells—**site shell → section shell (e.g. showcase) → page chrome → narrow content**—without authors manually threading `hx-target`, `hx-select`, and fragment block names through every link and handler.

**Concrete example:** b-site has a **marketing site shell** (`pages/_layout.html`, `{# target: body #}`) with `#site-content` as its outlet, and a **showcase app shell** (`pages/showcase/_layout.html`, `{# target: main #}`) that renders a full chirp-ui `app_shell()` nested inside it. A link from `/` to `/showcase` must replace `#site-content` (wide swap); a link from `/showcase` to `/showcase/products` must replace the *inner* showcase outlet (narrow swap). Today, both links need manually-chosen `hx-target` values—there is no framework-level reasoning about "which shell boundary this navigation crosses."

Today:

1. **Swap scope is implicit in DOM ids and headers**, not declared as *which shell level* is mutable for a given navigation. Authors must know that `#main` vs `#page-root` vs `#page-content-inner` correspond to different “widths” of swap, and must keep templates, registry entries, and links aligned.

2. **`LayoutChain` encodes depth** (`LayoutInfo.depth`, `find_start_index_for_target`), but there is **no symbolic vocabulary** tying a layout level to a *named swap scope* (e.g. `shell` / `page` / `content`) that tools and helpers can use consistently.

3. **`FragmentTargetRegistry` maps target ids → blocks**, and chirp-ui registers a **single** `PageShellContract` (`use_chirp_ui` → `CHIRPUI_PAGE_SHELL_CONTRACT`). Secondary shells (for example a showcase section) must register **additional** targets manually; the framework does not treat “each layout level owns one outlet” as a structured contract.

4. **Ordinary GET navigation** (boosted links) should ideally **derive the correct outlet** from **current path**, **destination path**, and the **deepest shared layout/shell**, letting authors avoid hand-authoring `hx-target` for every `<a>`. That derivation is not a client-side router; it is server-first route geometry. Nothing in Chirp exposes it as a supported interface yet.

5. **OOB scope is binary, not hierarchical.** `_triggers_shell_update` returns a flat `bool`—either shell regions refresh or they don't. In a multi-shell app, a swap inside the showcase shell should update *showcase-level* OOB regions (sidebar, breadcrumbs scoped to showcase) but **not** site-level chrome. The current model has no way to express "update OOB at *this* shell level only."

The [UI layers guide](/site/content/docs/guides/ui-layers.md) already names L1–L4 (app shell, shell outlet, page chrome, surface chrome). This RFC proposes making **which layer is the active swap scope for a given transition** a **first-class, checkable framework contract**, not just documentation.

---

## Goals

1. **Hierarchical outlets**: At each nesting level, the framework’s contract should be: **immutable frame + exactly one primary mutable outlet** (the region you swap for navigations that only replace content “inside” that shell).

2. **Narrowing swaps**: When navigation crosses from a parent shell into a child shell, the **effective swap scope moves inward** to the deepest **shared** shell frame, then **narrows** to the child outlet when both routes live under the same deeper shell.

3. **Symbolic scopes over raw selectors**: Expose **symbolic fragment scopes** (e.g. `shell`, `page`, `content`) mapped to **concrete target ids + fragment blocks** per app/contract. **Numeric depth** remains a useful *mental model* (0 = root layout); the **public contract** should prefer **names** for stability and readability.

4. **Route-aware resolution**: Provide a **route-aware helper** that, given **current path**, **destination `href`**, and the **discovered layout / registry metadata**, returns the **recommended `hx-target` (or symbolic scope)** for boosted GET navigation—without introducing a client-side router or changing the server-only rendering model.

5. **Preserve server-first HTMX**: All behavior remains **request/response** driven; **no** proposal for `pushState`-style client routing or SPA-style route tables in the browser.

### Non-Goals

- **Client-side routers** or **path-to-component** frameworks in JS.
- **Replacing** `HX-Target` at the HTTP layer (headers remain the source of truth at runtime).
- **Mandatory** migration of every template in one release; contracts should be **adoptable incrementally**.

---

## Current State

### `LayoutInfo` and `LayoutChain`

`LayoutInfo` records each filesystem layout’s template, **`target`** (the DOM element id that layout renders *into*), and **`depth`**. `LayoutChain` orders layouts **root → leaf** and implements `find_start_index_for_target(htmx_target)` so the render plan can find **which layout to start from** when `HX-Target` matches a layout’s `target`.

```86:137:src/chirp/pages/types.py
class LayoutInfo:
    ...
    template_name: str
    target: str
    depth: int
...
class LayoutChain:
    ...
    def find_start_index_for_target(self, htmx_target: str | None) -> int | None:
        ...
```

This is the geometric backbone for **nested shells**: each layout’s `target` is the **socket** the next layer fills.

### `FragmentTargetRegistry` and `PageShellContract`

The registry maps **target id** → `FragmentTargetConfig` (`fragment_block`, `triggers_shell_update`, …). `PageShellContract` groups targets for **contract checking** and bulk registration.

```60:113:src/chirp/templating/fragment_target_registry.py
class FragmentTargetRegistry:
    ...
    def register_contract(self, contract: PageShellContract) -> None:
        ...
        if self._contracts and contract.name not in self._contracts:
            msg = (
                "Only one page shell contract can be registered per app today. "
                "Register fragment targets directly for secondary shells."
            )
            raise ValueError(msg)
```

**Implication:** Multi-shell apps today rely on **`register_fragment_target` for extra targets**; a **second named contract** is blocked. Hierarchical shell scopes need a **first-class multi-contract or scoped-registration story** (see Decision).

### Render plan

`build_render_plan()` combines:

- **`_compute_layout_start_index`** — uses `LayoutChain` + `HX-Target` for boosted fragments.
- **`_fragment_block_for_request` / `_resolve_fragment_block`** — uses `FragmentTargetRegistry` (and explicit `PageComposition.fragment_block`) to pick the **Kida block**.

```161:174:src/chirp/templating/render_plan.py
def _compute_layout_start_index(
    layout_chain: LayoutChain | None,
    htmx_target: str | None,
    is_history_restore: bool,
) -> int:
    """Compute layout start index for HX-Target-aware depth."""
    ...
    idx = layout_chain.find_start_index_for_target(htmx_target)
    if idx is None:
        return len(layout_chain.layouts)
    return idx
```

```205:275:src/chirp/templating/render_plan.py
def build_render_plan(
    composition: PageComposition,
    *,
    request: Request | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    shell_region_updates: tuple[RegionUpdate, ...] = (),
) -> RenderPlan:
    ...
```

Note: `render_plan.py` also defines `LayoutContract` and `OOBBlockInfo` (lines 30–45)—frozen dataclasses that cache per-layout OOB metadata. These are relevant to Phase 4 (contract checking) as they already model "which OOB blocks does a layout provide."

Shell **OOB** refresh is gated by `triggers_shell_update` (see below).

### Negotiation: shell updates

`compute_shell_region_updates` and `_triggers_shell_update` tie **fragment swaps** to **`shell_actions`** (and related) OOB when the **registered target** allows it:

```23:68:src/chirp/server/negotiation_oob.py
def _triggers_shell_update(
    request: Request | None,
    fragment_target_registry: FragmentTargetRegistry | None,
) -> bool:
    ...
    config = fragment_target_registry.get(request.htmx_target)
    return config is not None and config.triggers_shell_update
```

**Scope** is not only “which block renders”; it also affects **whether** topbar/shell regions update.

### chirp-ui shell contract registration

`use_chirp_ui` registers `CHIRPUI_PAGE_SHELL_CONTRACT` with targets `main`, `page-root`, `page-content-inner` mapping to `page_root`, `page_root_inner`, `page_content` with selective `triggers_shell_update`.

```41:62:src/chirp/ext/chirp_ui.py
CHIRPUI_PAGE_SHELL_CONTRACT = PageShellContract(
    name="chirpui-app-shell",
    ...
    targets=(
        PageShellTarget(target_id="main", fragment_block="page_root", ...),
        PageShellTarget(target_id="page-root", fragment_block="page_root_inner", ...),
        PageShellTarget(
            target_id="page-content-inner",
            fragment_block="page_content",
            triggers_shell_update=False,
            ...
        ),
    ),
)
```

### Vocabulary: UI layers

The docs define **L1–L4** (app shell, shell outlet, page chrome, surface chrome) and tie **fragment targets** and **OOB** to those layers. This RFC aligns **symbolic scopes** with that vocabulary so **guides, public interfaces, and contracts** say the same thing.

---

## Decision

### 1. Shell scope metadata on layouts

**Extend layout discovery** so each `LayoutInfo` (or a parallel structure) can carry optional **shell scope** metadata:

- **`swap_scope_name`** — Symbolic name: `shell` \| `page` \| `content` \| app-defined.
- **`outlet_target_id`** — DOM id of the **primary navigation outlet** for this layout level (may default to `{# target: ... #}`).
- **`frame_targets`** — Optional set of ids treated as **frame** (immutable across swaps at this level) for validation.

**Principle:** Each layout level **owns one primary outlet** for **cross-route** navigation under that part of the route tree. Nested layouts **narrow** the default outlet for descendants.

### 2. Symbolic fragment scopes (`shell` / `page` / `content`)

Define a small **framework `enum` or string registry** of **well-known symbolic scopes** that map to:

- a **concrete `hx-target` id** (after registry normalization), and
- a **`FragmentTargetRegistry`** entry (fragment block + `triggers_shell_update`).

**Numeric levels** (`LayoutInfo.depth`) remain useful for **debugging and documentation**, but **templates and helpers should use symbolic names** so refactors can rename ids without breaking author intent.

Example mapping (illustrative; exact ids remain app-defined):

| Symbolic scope | Typical role                     | Example target id (chirp-ui) |
| -------------- | -------------------------------- | ---------------------------- |
| `shell`        | L1–L2: swap inside site chrome   | `#main`                      |
| `page`         | L3: tabbed/page chrome           | `#page-root`                 |
| `content`      | L4: narrow in-page               | `#page-content-inner`        |

**Extensibility:** Three canonical names cover two-level apps (site shell + app shell). Apps with **three or more** nesting levels (site → showcase → sub-section) need **app-defined scope names** (e.g. `section`). The registry should accept arbitrary strings and validate them against `FragmentTargetRegistry` entries; the three canonical names are **well-known defaults**, not a closed set. Custom scopes should participate in the same resolution and contract-checking machinery.

### 3. Route-aware swap resolution helper

Add a **pure function** (names tentative) usable at **template render time** or from **context factories**:

```python
def resolve_navigation_swap(
    *,
    current_path: str,
    destination_href: str,
    layout_chain: LayoutChain,
    registry: FragmentTargetRegistry,
) -> SwapResolution: ...
```

**`SwapResolution`** should include at minimum:

- `htmx_target: str` — value suitable for `hx-target` (with `#` prefix per convention)
- `scope: str` — symbolic scope name
- `fragment_block: str | None` — resolved block if derivable without a request

**Algorithm (conceptual):**

1. Compute **deepest shared layout prefix** between **current** and **destination** route’s `LayoutChain` (by filesystem path or discovered layout sequence).
2. If the navigation **exits** a nested route (for example leaves `/showcase/...` for `/`), the **default outlet** is the **outermost shared shell’s** outlet (`shell`).
3. If the navigation **stays** within a nested shell, the default outlet is that shell’s **inner** outlet (`page` or `content` per metadata).
4. Consult `FragmentTargetRegistry` to ensure the target is **registered**; if not, **fall back** with explicit logging (same class of diagnostics as today’s unregistered `HX-Target` debug log).

This is **not** a client router: it **emits attributes** for HTMX; the **server** still validates via `HX-Target` and the render plan.

**Template-side ergonomics (illustrative):**

```html
{# Today: author must know the right id for every link #}
<a href="/showcase/products" hx-target="#main" hx-boost="true">Products</a>

{# Proposed: framework resolves scope from route geometry #}
<a href="/showcase/products" {{ swap_attrs("/showcase/products") | html_attrs }}>Products</a>
```

Where `swap_attrs` is a template global (or filter) wrapping `resolve_navigation_swap` with the current request path and layout metadata already bound. Output: `hx-target="#main" hx-boost="true"` (or narrower, depending on context). Explicit `hx-target` on the element always wins (escape hatch).

**Edge cases:**

- **No layout chain (standalone route):** Resolution returns `None`; no `hx-target` emitted. The link behaves as a normal full-page navigation. This preserves backward compatibility for apps that don't use filesystem layouts.
- **Deep → root navigation (e.g. `/showcase/products/42` → `/`):** The shared layout prefix is just the root layout. Resolution promotes to the widest outlet (`shell` or equivalent). The entire inner shell is replaced.
- **Same route (current == destination):** Resolution returns `None` or the **narrowest** registered scope. Useful for "refresh" patterns but should not emit `hx-target` by default—avoids redundant swaps.
- **Destination not in route table (external or unresolved):** Resolution returns `None` with a debug log. No attributes emitted; link falls through to normal navigation.

### 4. Contract checking

Extend contract checks so that for each registered **scope** or **layout level**:

- the **outlet id** exists in templates (or is declared OOB-only where appropriate),
- **nested** layouts do not declare **conflicting** default outlets for the same route branch,
- **boosted** links that declare explicit `hx-target` **override** the helper (escape hatch).

### 5. Multi-shell registration (evolve registry)

Relax or replace the **“only one `PageShellContract`”** restriction so that **section shells** (e.g. showcase) can register a **named contract** scoped to a **URL prefix** or **layout depth**, without losing validation. Until then, the RFC recommends **`register_fragment_target` for secondary shells** with documented ids—**current behavior**—while **tracking** the gap as technical debt.

### 6. Scoped OOB propagation

Tie OOB region updates to **shell scope level**. When a swap targets an inner shell's outlet, the framework should fire OOB blocks for **that shell and its ancestors**, but **not** for sibling or descendant shells that aren't part of the current transition. This extends the existing `triggers_shell_update` boolean into a **scope-aware** decision: each contract (or layout level) declares which OOB regions it owns, and `compute_shell_region_updates` filters to the appropriate set based on the matched scope.

This builds on `LayoutContract` and `OOBBlockInfo` (already in `render_plan.py`, lines 30-45) which cache per-layout OOB metadata. The missing piece is connecting **which layout's OOB blocks fire** to the **swap scope** of the current request.

---

## Navigation Examples

Concrete **default outlet** behavior for boosted GET navigation (assuming a **site shell** at `/` and a **showcase shell** under `/showcase` with its own outlet inside `#main`):

- **From `/` → `/showcase`** — Deepest shared shell: site root only. Default swap scope: **Site** — replace shell outlet (L2). Typical `hx-target` role: outermost outlet (e.g. `#main` / `shell`).
- **From `/showcase` → `/showcase/products`** — Deepest shared shell: site + showcase layouts. Default swap scope: **Showcase** — replace **section** outlet. Typical `hx-target` role: inner outlet under showcase (e.g. `page` / dedicated `#showcase-outlet`).
- **From `/showcase/products` → `/showcase/products/{id}`** — Deepest shared shell: same product section. Default swap scope: **Page chrome** — tabs/title region. Typical `hx-target` role: `#page-root` or section’s `page` scope.
- **Same route family: in-page table → detail pane (narrow)** — Deepest shared shell: same. Default swap scope: **Content**. Typical `hx-target` role: `#page-content-inner` / `content`.

**Narrowing rule:** The framework chooses the **deepest outlet** that must change for the **destination** while preserving **shared** outer frames. **Cross-family** jumps promote the swap to a **wider** outlet.

---

## Backward Compatibility

- Existing apps that **manually set** `hx-target` / `hx-select` continue to work; resolution helpers are **opt-in**.
- **`FragmentTargetRegistry`**, **`build_render_plan`**, and **`HX-Target`** semantics remain the **runtime** contract; new metadata **feeds** those paths, not replace them.
- chirp-ui’s **`CHIRPUI_PAGE_SHELL_CONTRACT`** remains the **default** L1–L3 mapping; additive **layout metadata** must **default to “no change”** when absent.

---

## Implementation Plan

### Phase 1: Types and discovery — DONE

`LayoutInfo` now carries `swap_scope_name`, `outlet_target_id`, and `frame_targets` (all optional, defaulting to `None`). Layout discovery in `discovery.py` parses `{# swap_scope: #}`, `{# outlet: #}`, and `{# frames: #}` comments and populates these fields.

- [x] Optional **shell scope** fields on `LayoutInfo`.
- [x] Discovery regex parsing for new layout comments.
- [x] **`LayoutChain.find_start_index_for_target`** matches **`outlet_target_id`** as well as **`target`**, so `HX-Target: #main` resolves for chirp-ui shells where the layout declares `{# target: body #}` and `{# outlet: main #}` (see `site/content/docs/routing/filesystem-routing.md` and `examples/chirpui/pages_shell/pages/_layout.html`).

### Phase 2: Registry and contracts — DONE

The single-contract restriction has been lifted. `register_contract` now accepts multiple named contracts; target ids must be unique across the registry (later registrations override). `App.register_swap_scope(scope, target_id)` maps symbolic scope names to concrete target ids. chirp-ui registers `shell`, `page`, `content` during `use_chirp_ui`.

- [x] Multiple named shell contracts.
- [x] `register_swap_scope` on `App`.
- [x] chirp-ui default scope registration.

### Phase 3: `resolve_navigation_swap` — DONE

`SwapResolution` dataclass and `resolve_navigation_swap` pure function live in `src/chirp/templating/navigation_swap.py`. The function takes both routes' `LayoutChain`s, the `FragmentTargetRegistry`, and the `swap_scope_map`, then computes the deepest shared layout prefix to derive the recommended `hx-target` and symbolic scope. `swap_attrs` template global is wired via the compiler.

- [x] `SwapResolution` frozen dataclass.
- [x] `resolve_navigation_swap` pure function with shared-prefix algorithm.
- [x] `swap_attrs(href)` template global bound at render time.
- [x] Route table introspection via compiler wiring.

### Phase 4: Contract checker — DONE

`rules_layout.py` validates all scope metadata. `check_layout_chains` now accepts `fragment_target_registry` to cross-reference frame targets against registered swap targets.

- [x] Duplicate `swap_scope` per layout chain.
- [x] Validate `outlet_target_id` exists in templates (category `layout_outlet`).
- [x] Validate `frame_targets` are not registered as swap targets (category `layout_frame`).
- [x] Warn on conflicting `outlet_target_id` at the same depth (category `layout_outlet`).

### Phase 5: Docs — DONE

`site/content/docs/guides/ui-layers.md` updated with symbolic scope vocabulary, layout comments reference, `swap_attrs` template global, nested shell example (b-site), scoped OOB explanation, and contract check summary.

- [x] **UI layers** guide with symbolic scope vocabulary and scope table.
- [x] Layout comments reference (`{# swap_scope #}`, `{# outlet #}`, `{# frames #}`).
- [x] `swap_attrs` template global usage and before/after example.
- [x] Nested-shell example (b-site marketing shell + showcase app shell).
- [x] Scoped OOB and contract checks sections.

### Decision 6: Scoped OOB propagation — DONE

`scope_name` field added to `PageShellTarget` and `FragmentTargetConfig`. `resolve_oob_scope` in `negotiation_oob.py` extracts the scope from the current request's target. `RenderPlan` carries `oob_scope` which the layout OOB loop in `execute_render_plan` uses to filter: when a scope is set, only OOB blocks from layouts at or above that scope's depth fire.

- [x] `scope_name` on `PageShellTarget` and `FragmentTargetConfig`.
- [x] `resolve_oob_scope` helper in `negotiation_oob.py`.
- [x] `oob_scope` on `RenderPlan`, populated from `fragment_target_registry`.
- [x] Layout OOB loop filters by `max_oob_depth` when scope is set.
- [x] chirp-ui `CHIRPUI_PAGE_SHELL_CONTRACT` targets declare `scope_name`.

---

## Alternatives Considered

### A. Depth-only scheme (`swap_level=2`)

**Rejected as the primary approach:** Integers shift when a layout is inserted; **symbolic names** are stable across refactors. **Depth** remains a **secondary** diagnostic.

### B. Encode scope only in `hx-select` strings

**Rejected:** Selectors are **fragile** and **template-local**; the framework should own **route-level** semantics, not CSS selector strings in every link.

### C. Per-route `fragment_block` only

**Insufficient:** Solves **rendering** width but not **author ergonomics** for **which** outlet to target on **navigation**; the hierarchical problem is **cross-route**, not only **per handler**.

---

## Open Questions

1. **Resolution inputs:** Should `resolve_navigation_swap` take **only paths**, or also **`RouteMeta`** / section ids when the route contract RFC matures?

2. **Prefix-scoped contracts:** Is the cleanest implementation **URL-prefix → contract**, or **layout template name → contract**?

3. **Non-boosted navigation:** Should full page loads **ignore** symbolic scopes entirely (today: yes), or should **progressive enhancement** helpers still emit **consistent** `data-*` for tests?

4. **Testing:** What **golden fixtures** best encode nested shells (minimal three-level layout chain in `tests/`)?

5. **Route table introspection shape:** Should `resolve_navigation_swap` query a **frozen dict** (`path → LayoutChain`) built at freeze time, or a **prefix-tree** that matches dynamic segments? The frozen-dict approach is simpler but fails for parameterized routes (`/products/{id}`); the prefix-tree handles them but adds complexity. This is the **blocking prerequisite** for Phase 3.

6. **OOB scope propagation:** When a swap targets an inner shell's outlet, which shell level's OOB blocks should fire? Today `_triggers_shell_update` is all-or-nothing. Should each `PageShellContract` declare its own OOB regions, with the framework only firing OOB for the **matched scope and its ancestors** (not siblings or descendants)?

---

## Success Criteria

- Authors can describe nested shells using **layout metadata + symbolic scopes** without manually synchronizing **three** places (template id, registry, every link).
- **Boosted** navigation defaults can be **derived** from **current + destination** paths for common patterns (site → section → page).
- Contract checks catch **missing outlets** and **ambiguous** nested scopes at **freeze** time where possible.
- **No** client-side router; **no** regression in **server-driven** HTMX semantics.
- Documentation (**UI layers**) and **public interface names** align on **shell / page / content** vocabulary.

---

## References

### Source files

- `src/chirp/pages/types.py` — `LayoutInfo`, `LayoutChain`, `find_start_index_for_target`
- `src/chirp/templating/fragment_target_registry.py` — `FragmentTargetRegistry`, `PageShellContract`, `FragmentTargetConfig`
- `src/chirp/templating/render_plan.py` — `build_render_plan`, `_compute_layout_start_index`, `_resolve_fragment_block`, `_fragment_block_for_request`, `LayoutContract`, `OOBBlockInfo`
- `src/chirp/server/negotiation_oob.py` — `_triggers_shell_update`, `compute_shell_region_updates`
- `src/chirp/ext/chirp_ui.py` — `CHIRPUI_PAGE_SHELL_CONTRACT`, `use_chirp_ui`

### Evidence: b-site nested shells

- `b-site/pages/_layout.html` — root marketing shell (`{# target: body #}`, outlet `#site-content`)
- `b-site/pages/showcase/_layout.html` — nested showcase shell (`{# target: main #}`, renders chirp-ui `app_shell()` inside site shell)

### Documentation

- `site/content/docs/guides/ui-layers.md` — L1–L4 vocabulary, fragment targets vs shell

### Related RFCs

- RFC: Implicit Fragment Resolution — registry + render plan interaction
- RFC: Route Directory Contract — route directory as metadata unit (complementary)
