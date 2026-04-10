# RFC: Route Directory Contract

**Status**: Draft  
**Date**: 2026-03-11  
**Scope**: `src/chirp/pages/`, `src/chirp/contracts/`, `src/chirp/app/`  
**Related**: [Chirp Route Contract Vision](/.cursor/plans/chirp-route-contract-vision_2b982af5.plan.md), RFC: Contract Validation Extensions, RFC: Server-First App-Shell Stability  
**Reference App**: Dori dashboard (`src/dori/dashboard/pages/`)

---

## Problem

Chirp's filesystem routing already discovers `page.py`, `_context.py`, and `_layout.html` and wires them into a context cascade, layout chain, and render plan. This machinery works. But the route directory as a unit has no formal contract — the framework knows about individual files, not about the route as a whole.

The consequences show up in every Chirp app that grows past a few routes:

### 1. Shell context is app-local glue

Every Dori page handler takes `breadcrumb_prefix` and `route_tabs` from the cascade, then manually calls `build_page_context()` to assemble `current_path`, `sidebar_sections`, `breadcrumb_items`, `page_title`, and `tab_items`. This wrapper exists because the framework does not own shell context assembly.

Evidence — Dori's `page_context.py`:

```python
def build_page_context(
    request: Request,
    *,
    page_title: str,
    breadcrumb_prefix: Sequence[BreadcrumbItem] = (),
    breadcrumb_suffix: Sequence[BreadcrumbItem] = (),
    tab_items: Sequence[object] = (),
    shell_actions: object | None = None,
    **extra: Any,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "current_path": request.path,
        "page_title": page_title,
        "breadcrumb_items": [*breadcrumb_prefix, *breadcrumb_suffix],
        "tab_items": tuple(tab_items),
        "route_tabs": tuple(tab_items),
        "sidebar_sections": dashboard_sidebar_sections(request.path),
    }
    if shell_actions is not None:
        context["shell_actions"] = shell_actions
    context.update(extra)
    return context
```

Every page handler in Dori calls this. The same pattern would repeat in any Chirp app with a persistent shell.

### 2. Section identity is tribal knowledge

Dori maintains a `DashboardSection` registry in `navigation.py` with `active_prefixes`, `active_exact_paths`, `tab_items`, and `breadcrumb_prefix`. Most `_context.py` files exist solely to call `section_context("discover")` or `section_context("settings")`:

```python
# skills/_context.py, workspace/_context.py, chains/_context.py, ...
def context() -> dict:
    return section_context("discover")
```

Section membership, tab families, and breadcrumb prefixes are route-level facts, but the framework has no concept of them.

### 3. No reserved file vocabulary beyond three files

Discovery recognizes `page.py` (and sibling `.py` route files), `_context.py`, and `_layout.html`. But apps need more route-local structure:

- **Route metadata** (title, section, auth level, cache hints) lives in handler code or `_context.py` as ad hoc dict keys.
- **Mutation handlers** (POST, form actions) are mixed into `page.py` alongside GET display logic.
- **View assembly** (building the context dict from multiple data sources) clutters transport-focused handlers.

There is no sanctioned place for these concerns, so every app invents its own conventions.

### 4. Route kind is implicit

A `page.py` that returns a dict-with-template behaves differently from one that returns `PageComposition`, which behaves differently from a redirect or a pure-action route. The framework infers behavior from the return type at runtime. There is no static vocabulary for route kinds, and no way to validate that a route's files are consistent with its kind.

### 5. Shell contract validation is block-deep, not context-deep

`rules_page_shell.py` validates that page templates define the required fragment blocks (`page_root`, `page_root_inner`, `page_content`). But it cannot validate that routes provide the context keys those blocks need (`page_title`, `breadcrumb_items`, `tab_items`, `current_path`, etc.) because those keys are not part of any contract — they are informal conventions between `_context.py`, `page.py`, and templates.

---

## Goals

1. **Define the route directory contract**: a formal vocabulary of reserved files, their meanings, ownership rules, and inheritance semantics.
2. **Make route metadata declarative**: section identity, breadcrumbs, tab families, page title, auth level, shell mode, and cache hints should be statable as route-level facts, not handler-level wiring.
3. **Codify context merge rules**: formalize what `_context.py` receives, what it can return, how child overrides parent, and how `shell_actions` merges — as a contract, not just implementation detail.
4. **Define route kinds**: give static names to the common patterns (page route, detail route, action route, redirect route, composition route) so the framework can validate file combinations.
5. **Preserve backward compatibility**: existing `page.py` + `_context.py` + `_layout.html` apps must continue to work unchanged. The new reserved files are opt-in additions.

### Non-Goals

- **Runtime behavior changes**: this RFC defines contract vocabulary and validation. Render plan, layout chain, and fragment target resolution are unchanged.
- **`_fragments.py`**: intentionally deferred. Fragment response builders stay in `page.py` until a real app proves sprawl.
- **Sidebar generation**: sidebar section trees are app-level structure. The framework provides the metadata; apps compose the sidebar.
- **Breaking the dict-return shorthand**: handlers that return `dict` still get `upgrade_result`. `_meta.py` is additive context, not a replacement.

---

## Reserved Files

### Existing (unchanged)

| File | Scope | Purpose |
|------|-------|---------|
| `page.py` | route-local | Primary route handler. Exports HTTP-method functions (`get`, `post`, ...) or a `handler` fallback. `page.py` → directory URL; other `.py` files append their stem. |
| `page.html` | route-local | Primary page template. Discovered as sibling of `page.py`. Defines fragment blocks (`page_root`, `page_root_inner`, `page_content`). |
| `_context.py` | inherited | Subtree-scoped context provider. Exports `context()` which receives path params, accumulated parent context, and service providers. |
| `_layout.html` | inherited | Subtree layout wrapper. Declares `{# target: element_id #}` and `{% block content %}`. |

### New: `_meta.py` (route-local, optional)

Declarative route metadata. Exports a `meta()` function or a module-level `META` constant that returns a `RouteMeta` dataclass.

```python
from chirp.pages import RouteMeta

META = RouteMeta(
    title="Skills",
    section="discover",
    breadcrumb_label="Skills",
    shell_mode="tabbed",
)
```

Or as a function when metadata depends on path params or services:

```python
from chirp.pages import RouteMeta

def meta(name: str, orchestrator: DORIOrchestrator) -> RouteMeta:
    skill = orchestrator.get_skill(name)
    return RouteMeta(
        title=skill.display_name if skill else name,
        breadcrumb_label=skill.display_name if skill else name,
    )
```

**What `RouteMeta` contains:**

```python
@dataclass(frozen=True, slots=True)
class RouteMeta:
    title: str | None = None
    section: str | None = None
    breadcrumb_label: str | None = None
    shell_mode: str | None = None       # e.g. "tabbed", "full", "minimal"
    auth: str | None = None             # e.g. "required", "optional", "none"
    cache: str | None = None            # e.g. "static", "per-request", "private"
    tags: tuple[str, ...] = ()          # arbitrary route tags for introspection
```

**Inheritance:** `_meta.py` is **not inherited**. Each route declares its own metadata. Section-level defaults come from `_context.py` (which inherits) or from the section registry.

**Why a separate file:** Metadata is a different concern from context computation. `_context.py` runs code (loads data, raises `NotFound`, injects services). `_meta.py` states facts. Keeping them separate means:

- `_meta.py` can be loaded and validated at startup without executing side effects.
- Route introspection can read metadata without triggering context providers.
- The framework can build breadcrumb chains and section maps from metadata alone.

### New: `_actions.py` (route-local, optional)

Named mutation handlers for the route. Exports functions decorated with `@action` or named by convention.

```python
from chirp.pages import action

@action("delete")
async def delete(request: Request, name: str, orchestrator: DORIOrchestrator) -> Redirect:
    orchestrator.delete_skill(name)
    return Redirect("/skills")

@action("run")
async def run(request: Request, name: str, orchestrator: DORIOrchestrator) -> Fragment:
    result = await orchestrator.run_skill(name)
    return Fragment("skill/{name}/page.html", "run_result", context={"result": result})
```

**Discovery:** `_actions.py` is scanned at startup. Each `@action` function is registered as a POST handler at the route URL with a discriminator (e.g., form `action` field or query param).

**Argument resolution:** Same as `page.py` and `_context.py` — path params, accumulated context, service providers.

**Fragment responses from actions:** Actions may return `Fragment`, `Redirect`, `Page`, or `OOB`. Fragment targets follow the same render plan as `page.py` responses.

**Relationship to `page.py`:** If `page.py` already exports `post()`, that is the route's POST handler. `_actions.py` provides named sub-actions dispatched within the POST method. If both exist, `_actions.py` actions are registered as named sub-actions; `page.py`'s `post()` is the default POST handler.

**Why a separate file:** Mutation logic (delete, approve, run, toggle) is a different concern from display logic (list, detail, search). Separating them:

- Makes it clear which route has mutations and what they are.
- Prevents `page.py` from growing into a monolith of GET + POST + form handling.
- Gives actions a consistent dispatch pattern instead of per-handler `if action == "delete"` branching.

### New: `_viewmodel.py` (route-local, optional)

View assembly when `page.py` should stay transport-focused. Exports a `viewmodel()` function that receives the same inputs as a handler but returns a context dict.

```python
from chirp.pages import RouteMeta

def viewmodel(
    request: Request,
    orchestrator: DORIOrchestrator,
    breadcrumb_prefix: list,
) -> dict:
    skills = orchestrator.list_skills()
    return {
        "skills": skills,
        "total_count": len(skills),
        "has_remote": any(s.is_remote for s in skills),
    }
```

**When to use:** When the context dict is complex enough that it obscures the handler's transport logic (status codes, redirects, content negotiation). For simple routes, building the dict in `page.py` is fine.

**Relationship to `page.py`:** If `_viewmodel.py` exists, its output is merged into the handler's context before template rendering. The handler can override any key. If the handler returns a plain dict, the viewmodel's output is the base; the handler's dict overrides it.

### Deferred: `_fragments.py`

Intentionally not introduced in phase 1. Fragment response builders stay in `page.py` (or `_actions.py` for mutation-triggered fragments). The decision gate for `_fragments.py` is: when a real app shows repeated fragment-builder functions in `page.py` that are not mutations and not display logic, reconsider.

---

## Route Kinds

A route's **kind** is inferred from its file combination and handler signatures. The framework assigns a kind during discovery and can validate that the files are consistent.

| Kind | Required Files | Optional Files | Handler Returns |
|------|---------------|----------------|-----------------|
| **page** | `page.py`, `page.html` | `_context.py`, `_layout.html`, `_meta.py`, `_viewmodel.py`, `_actions.py` | `dict`, `Page`, `PageComposition` |
| **detail** | `page.py`, `page.html` in `{param}/` dir | `_context.py`, `_meta.py`, `_viewmodel.py`, `_actions.py` | `dict`, `Page`, `PageComposition` |
| **action** | `page.py` (no `page.html`) | `_context.py`, `_meta.py` | `Redirect`, `Fragment`, `OOB`, status tuple |
| **redirect** | `page.py` (no `page.html`) | — | `Redirect` |
| **composition** | `page.py`, `page.html` | `_context.py`, `_meta.py` | `PageComposition` |

Route kind is informational in phase 1. It enables better error messages, introspection, and future validation (e.g., warning when an action route has a `page.html` it never renders).

---

## Inheritance and Merge Rules

### Context Cascade (existing, now codified)

Providers run root → leaf. Each provider's output merges into the accumulated context:

| Key | Merge Rule |
|-----|-----------|
| `shell_actions` | Deep merge via `merge_shell_actions()`: zones merge by `mode` (merge/replace), actions merge by `id`, `remove` list filters inherited actions. |
| All other keys | Child overrides parent (last-writer-wins). |

**Provider argument resolution order:**

1. Path params from URL match
2. Accumulated context from parent providers
3. Service providers from `app.provide()` by type annotation

This is already implemented in `chirp/pages/context.py:99-120`. The RFC codifies it as the contract.

### Layout Chain (existing, now codified)

Layouts stack root → leaf. Each layout declares a `target` element ID. The render plan uses `HX-Target` to find the starting layout depth.

| Request Type | Layout Behavior |
|-------------|-----------------|
| Full page (no HX headers) | Render all layouts, outermost to innermost |
| Boosted navigation (`HX-Boosted`) | Render from layout matching `HX-Target` |
| Page fragment (boosted + target in layout chain) | Render from matching layout |
| Local fragment (target not in layout chain) | Skip all layouts, render block only |

This is already implemented in `chirp/templating/render_plan.py:143-157`. The RFC codifies it as the contract.

### Metadata (new)

`_meta.py` is **not inherited**. Each route owns its metadata. Section-scoped defaults (tab items, breadcrumb prefix) are derived from section membership, not from `_meta.py` inheritance.

**Resolution order for shell context keys:**

| Key | Source | Fallback |
|-----|--------|----------|
| `page_title` | `RouteMeta.title` | Handler return dict `page_title` key |
| `breadcrumb_items` | Section breadcrumb prefix + `RouteMeta.breadcrumb_label` + handler suffix | Handler return dict `breadcrumb_items` key |
| `tab_items` | Section tab items from section registry | Handler return dict `tab_items` key |
| `current_path` | `request.path` (always injected by framework) | — |
| `shell_actions` | Cascade context merge | Handler return dict override |

**Key principle:** The framework assembles shell context from route metadata, section registry, and cascade context. Handlers only provide page-specific data. If a handler returns a key that the framework also provides, the handler's value wins.

### Viewmodel (new)

If `_viewmodel.py` exists:

1. Cascade context runs first (root → leaf `_context.py`).
2. `_meta.py` is loaded (static or function).
3. `_viewmodel.py` runs, receiving cascade context, path params, and services.
4. Handler runs, receiving viewmodel output merged into cascade context.
5. Handler's return dict overrides viewmodel keys.

If `_viewmodel.py` does not exist, behavior is unchanged from today.

---

## Section Registry

Sections are groups of routes that share tab families, breadcrumb prefixes, and active-state logic. Today this is app-local (`navigation.py` in Dori). The route contract introduces a framework-level section concept.

### Registration

```python
app.register_section(
    Section(
        id="discover",
        label="Discover",
        tab_items=(
            TabItem(label="Skills", href="/skills"),
            TabItem(label="Shortcuts", href="/shortcuts"),
        ),
        breadcrumb_prefix=({"label": "Discover", "href": "/skills"},),
    )
)
```

### Route-to-Section Binding

Routes declare section membership in `_meta.py`:

```python
META = RouteMeta(section="discover")
```

Or sections declare route prefixes:

```python
Section(
    id="discover",
    active_prefixes=("/skills", "/shortcuts", "/skill/"),
    ...
)
```

Both approaches are supported. Explicit `_meta.py` wins over prefix matching.

### What the Framework Provides

When a route belongs to a section, the framework injects into the template context:

- `tab_items`: the section's tab items
- `breadcrumb_prefix`: the section's breadcrumb prefix (before the route's own label)

This eliminates most single-line `_context.py` shims:

```python
# BEFORE: skills/_context.py (5 lines of boilerplate)
def context() -> dict:
    return section_context("discover")

# AFTER: skills/_meta.py (3 lines of declaration)
META = RouteMeta(section="discover", breadcrumb_label="Skills")
```

---

## Context Contract Formalization

### What `_context.py` Can Receive

| Parameter Source | Resolution |
|-----------------|------------|
| Path params | From URL match (e.g., `name` from `/skill/{name}`) |
| Parent context keys | From accumulated cascade (e.g., `breadcrumb_prefix` from parent) |
| Service providers | From `app.provide()`, matched by type annotation |

### What `_context.py` Cannot Receive

- `request`: Context providers are request-independent by design. They receive path params (which come from the request URL) but not the full request object. This keeps context providers testable and cacheable.
- Framework-injected keys (`current_path`, `page_title` from `_meta.py`): These are assembled after the cascade, so they are not available during cascade execution.

### What `_context.py` Should Return

A dict of context keys. Recognized special keys:

| Key | Type | Merge Behavior |
|-----|------|---------------|
| `shell_actions` | `ShellActions` | Deep merge (zones by mode, actions by id) |
| All others | `Any` | Child overrides parent |

### What `_context.py` May Do

- Raise `NotFound`, `Forbidden`, or any `HTTPError` to abort the cascade. The framework renders the appropriate error page.
- Return data loaded from services (databases, APIs, caches).
- Return computed values derived from path params and parent context.

### What `_context.py` Should Not Do

- Assemble shell context (`page_title`, `breadcrumb_items`, `sidebar_sections`). That is the framework's job when `_meta.py` and sections are used.
- Return `tab_items` or `breadcrumb_prefix` when section membership handles it. This is the boilerplate the contract eliminates.

---

## Relationship to Existing Contracts

### Fragment Target Registry (unchanged)

`PageShellContract` registers required fragment blocks. `FragmentTargetRegistry` maps target IDs to blocks. The render plan uses the registry to resolve `HX-Target` to the correct block. None of this changes.

### Page Shell Rules (extended)

`rules_page_shell.py` currently validates that page templates define required fragment blocks. With the route contract, it gains an additional validation:

- Routes with `shell_mode="tabbed"` must have templates that define `page_root`, `page_root_inner`, and `page_content`.
- Routes with `shell_mode="full"` must define at least `page_root`.
- Routes with `shell_mode="minimal"` have no block requirements.

### Render Plan (unchanged)

The render plan's inputs (`PageComposition`, request, `FragmentTargetRegistry`) and logic are unchanged. The route contract feeds metadata into context assembly *before* the render plan runs, not into the render plan itself.

### Contract Checker (extended)

`check_hypermedia_surface()` gains new checks:

1. **Route file consistency**: warn if a page route has `_actions.py` but no `page.py`, or `_meta.py` in a directory with no route files.
2. **Section binding**: warn if `RouteMeta.section` references an unregistered section.
3. **Shell mode / block alignment**: error if `shell_mode="tabbed"` but template lacks required blocks.
4. **Metadata completeness**: info if a page route has no `_meta.py` (optional but recommended).

---

## Discovery Changes

### Current Discovery Flow

```
walk_directory(root)
  → for each directory:
      load _layout.html → LayoutInfo
      load _context.py  → ContextProvider
      for each .py file (not _prefixed):
        load module → handler functions
        find sibling .html → template_name
        build PageRoute
```

### Extended Discovery Flow

```
walk_directory(root)
  → for each directory:
      load _layout.html  → LayoutInfo              (existing)
      load _context.py   → ContextProvider          (existing)
      load _meta.py      → RouteMeta | MetaProvider (new)
      load _actions.py   → ActionRegistry           (new)
      load _viewmodel.py → ViewModelProvider        (new)
      for each .py file (not _prefixed):
        load module → handler functions             (existing)
        find sibling .html → template_name          (existing)
        build PageRoute with meta, actions, viewmodel (extended)
```

### `PageRoute` Extension

```python
@dataclass(frozen=True, slots=True)
class PageRoute:
    url_path: str
    handler: Callable[..., Any]
    methods: frozenset[str]
    layout_chain: LayoutChain = field(default_factory=LayoutChain)
    context_providers: tuple[ContextProvider, ...] = ()
    template_name: str | None = None
    name: str | None = None
    # New fields
    meta: RouteMeta | None = None
    meta_provider: Callable[..., RouteMeta] | None = None
    actions: tuple[ActionInfo, ...] = ()
    viewmodel_provider: Callable[..., dict] | None = None
    kind: RouteKind = "page"
```

---

## Handler Wrapper Changes

The `page_wrapper` in `registry.py` currently does:

```
cascade_ctx = build_cascade_context(providers, path_params, services)
kwargs = resolve_kwargs(handler, request, cascade_ctx, services)
result = invoke(handler, **kwargs)
return upgrade_result(result, cascade_ctx, layout_chain, ...)
```

With the route contract, it becomes:

```
cascade_ctx = build_cascade_context(providers, path_params, services)
meta = resolve_meta(meta, meta_provider, path_params, services)        # new
section_ctx = resolve_section_context(meta, section_registry)           # new
viewmodel_ctx = resolve_viewmodel(viewmodel_provider, cascade_ctx, ...) # new
merged_ctx = {**cascade_ctx, **section_ctx, **viewmodel_ctx}            # new
shell_ctx = build_shell_context(request, meta, merged_ctx)              # new
kwargs = resolve_kwargs(handler, request, {**merged_ctx, **shell_ctx}, services)
result = invoke(handler, **kwargs)
return upgrade_result(result, {**merged_ctx, **shell_ctx}, layout_chain, ...)
```

The handler still receives all context keys as potential kwargs. It can use or ignore them. Its return dict still overrides any framework-provided keys.

---

## Migration Path

### Fully Backward Compatible

Existing apps that use only `page.py`, `_context.py`, and `_layout.html` work without changes. The new files are opt-in.

### Incremental Adoption

Apps can adopt one new file at a time:

1. **Add `_meta.py`** to declare title and section. Remove those keys from `_context.py` return dict.
2. **Register sections** with `app.register_section()`. Remove `section_context()` calls from `_context.py`.
3. **Add `_actions.py`** to extract mutations from `page.py`. Keep `page.py` display-focused.
4. **Add `_viewmodel.py`** for complex context assembly. Simplify `page.py` to transport logic.

### Dori Migration Example

**Before** (current Dori pattern):

```python
# skills/_context.py
def context() -> dict:
    return section_context("discover")

# skills/page.py
def get(request, orchestrator, breadcrumb_prefix, route_tabs) -> dict:
    skills = orchestrator.list_skills()
    return build_page_context(
        request,
        page_title="Skills",
        breadcrumb_prefix=breadcrumb_prefix,
        breadcrumb_suffix=({"label": "Skills"},),
        tab_items=route_tabs,
        skills=skills,
        shell_actions=ShellActions(...),
    )
```

**After** (route contract):

```python
# skills/_meta.py
META = RouteMeta(
    title="Skills",
    section="discover",
    breadcrumb_label="Skills",
    shell_mode="tabbed",
)

# skills/page.py
def get(orchestrator: DORIOrchestrator) -> dict:
    skills = orchestrator.list_skills()
    return {
        "skills": skills,
        "shell_actions": ShellActions(...),
    }
```

No `_context.py` for section identity. No `build_page_context`. No `breadcrumb_prefix`/`route_tabs` in handler signature. The handler returns only page-specific data.

---

## Implementation Plan

### Step 1: `RouteMeta` Dataclass and Discovery

- Define `RouteMeta` in `chirp/pages/types.py`.
- Extend `discover_pages()` to scan for `_meta.py`.
- Load `META` constant or `meta()` function.
- Extend `PageRoute` with `meta` and `meta_provider` fields.
- Tests: discovery finds `_meta.py`, loads static and function forms, ignores missing.

### Step 2: Section Registry

- Define `Section` and `TabItem` in `chirp/pages/types.py`.
- Add `app.register_section()` to `AppRegistry`.
- Store sections in `MutableAppState`.
- Implement `resolve_section_context()` that maps `RouteMeta.section` → section's `tab_items` and `breadcrumb_prefix`.
- Tests: section registration, route-to-section binding, prefix matching fallback.

### Step 3: Shell Context Assembly

- Implement `build_shell_context()` that produces `page_title`, `breadcrumb_items`, `tab_items`, `current_path` from `RouteMeta`, section context, and cascade context.
- Update `page_wrapper` to call shell context assembly before handler invocation.
- Handler return dict overrides framework-provided keys.
- Tests: shell context assembly with and without `_meta.py`, override behavior, backward compatibility with existing apps.

### Step 4: `_actions.py` Discovery and Dispatch

- Define `@action` decorator and `ActionInfo` in `chirp/pages/actions.py`.
- Extend `discover_pages()` to scan for `_actions.py`.
- Register action handlers as named sub-routes or form-action dispatchers.
- Tests: action discovery, dispatch by name, argument resolution, fragment and redirect returns.

### Step 5: `_viewmodel.py` Discovery and Integration

- Extend `discover_pages()` to scan for `_viewmodel.py`.
- Integrate viewmodel output into the context merge chain.
- Tests: viewmodel runs before handler, handler overrides viewmodel keys.

### Step 6: Route Kind Inference

- Define `RouteKind` type in `chirp/pages/types.py`.
- Infer kind from file combination during discovery.
- Expose kind on `PageRoute` for introspection.
- Tests: correct kind inference for page, detail, action, redirect, composition routes.

### Step 7: Contract Checker Extensions

- Add route file consistency checks.
- Add section binding validation.
- Add shell mode / block alignment validation.
- Tests: contract violations produce correct issues.

---

## Phase 1 Fragment Rule

Fragment blocks live in `page.html` templates. Fragment response builders live in `page.py` (and in `_actions.py` for mutation-triggered fragments). `_fragments.py` is not introduced.

The decision gate for `_fragments.py`: when a real app (Dori or another) shows three or more non-mutation, non-display fragment-builder functions accumulating in `page.py`, reconsider.

---

## Testing Strategy

1. **Discovery tests**: New files are found and loaded. Missing files are ignored. Invalid files produce clear errors.
2. **Backward compatibility tests**: Existing apps with only `page.py` + `_context.py` + `_layout.html` produce identical behavior.
3. **Shell context tests**: `RouteMeta` + section → correct `page_title`, `breadcrumb_items`, `tab_items`. Handler override wins.
4. **Action dispatch tests**: `_actions.py` actions are discoverable and dispatchable. Argument resolution matches `page.py` conventions.
5. **Viewmodel tests**: Viewmodel output merges correctly. Handler overrides viewmodel keys.
6. **Contract checker tests**: Invalid file combinations, missing sections, shell mode / block mismatches → correct issues.
7. **Integration test**: A minimal app using all new files renders correctly for full-page, boosted, and fragment requests.

---

## Open Questions

1. **Action dispatch mechanism**: Should actions be dispatched by a hidden form field (`<input name="_action" value="delete">`), a query parameter (`?action=delete`), or a URL suffix (`/skills?action=delete`)? The form field approach is most HTML-native. The query parameter approach is simplest. Need to decide before implementing step 4.

2. **Section registration timing**: Should sections be registered before or after `mount_pages()`? Before is needed if discovery uses sections to infer metadata. After is simpler if sections are only used at runtime. Likely answer: before, since the contract checker needs section data at freeze time.

3. **`_meta.py` function form caching**: When `meta()` is a function that depends on path params, it runs per request. Should its output be cached per path-param combination? Likely answer: no caching in phase 1; add caching when profiling shows it matters.

4. **Breadcrumb chain assembly**: Should the framework automatically build the full breadcrumb chain from section prefix + `RouteMeta.breadcrumb_label`, or should it only provide the pieces and let the template assemble them? The former reduces boilerplate; the latter is more flexible. Likely answer: framework assembles by default, handler can override with `breadcrumb_items` key.

5. **`_viewmodel.py` vs. just using `_context.py`**: Is the distinction between "inherited context" and "route-local view assembly" clear enough to justify a separate file? Or should `_context.py` handle both? The argument for separation: `_context.py` is inherited and runs for the subtree, `_viewmodel.py` is route-local and runs only for the route's own requests.

---

## Success Criteria

- A new route directory can be understood by reading its files without consulting app-level glue modules.
- Section identity, tab families, and breadcrumb prefixes are declarative — not handler-level wiring.
- Dori's `navigation.py` and `page_context.py` shrink or disappear when migrated to the contract.
- Single-line `_context.py` shims (`return section_context("discover")`) are replaced by `_meta.py` declarations.
- The contract checker catches route file inconsistencies at startup.
- Existing Chirp apps work unchanged.

---

## References

- `src/chirp/pages/discovery.py` — current filesystem route discovery
- `src/chirp/pages/types.py` — `PageRoute`, `LayoutChain`, `ContextProvider`, `LayoutInfo`
- `src/chirp/pages/context.py` — cascade context builder
- `src/chirp/pages/shell_actions.py` — shell action models and merge logic
- `src/chirp/templating/fragment_target_registry.py` — fragment target and shell contract registry
- `src/chirp/templating/render_plan.py` — render plan builder and executor
- `src/chirp/contracts/checker.py` — contract validation orchestrator
- `src/chirp/contracts/rules_page_shell.py` — page shell block validation
- `src/chirp/ext/chirp_ui.py` — ChirpUI page shell contract registration
- `src/chirp/app/registry.py` — page handler wrapper and route registration
- Dori `src/dori/dashboard/navigation.py` — section registry (pain point)
- Dori `src/dori/dashboard/page_context.py` — shell context builder (pain point)
- Dori `src/dori/dashboard/pages/*/` — route directory patterns (pain points)
