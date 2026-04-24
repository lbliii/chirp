# RFC 003: Named Routes — Default Names for Page-Based Routes

**Status:** Draft
**Author:** (proposal)
**Created:** 2026-04-23
**Companions:** RFC 004 (`url_for`)

---

## 1. Problem Statement

`@app.route(path, *, name=...)` already accepts a name kwarg (`src/chirp/app/__init__.py:190-199`) and `PendingRoute.name` / `Route.name` fields already exist (`src/chirp/app/state.py:31`, `src/chirp/app/compiler.py:206`). But:

- **Page-discovery routes always register with `name=None`** (`src/chirp/app/registry.py:301`, `src/chirp/pages/discovery.py:585`) — so every route discovered from `pages/` is anonymous and cannot be referenced by name.
- **No lookup table by name exists** at the Router or App level — there's nowhere to build a `url_for` resolver against.

Without named routes populated by default, `url_for` (RFC 004) would be opt-in per route and users migrating a large app would still be editing every `@app.route` to add a name. The feedback prompting this work was a large IA refactor with 85 hardcoded URLs — opt-in naming would leave most of those orphaned.

---

## 2. Non-Goals

- Routes the user registers via `@app.route(path, name=...)` keep that behavior unchanged. This RFC only touches the default-naming behavior for page-discovery routes and adds a lookup table at freeze.
- No new decorator. No ceremony.
- No coupling to `url_for` semantics — RFC 004 owns that. This RFC only has to deliver a stable, unambiguous name per route.

---

## 3. Design Decisions

### 3.1 Default name for page-based routes

**Decision:** Derive a dotted name from the URL path, stripping parameter braces.

| URL path | Default name |
|----------|--------------|
| `/` | `"index"` |
| `/about` | `"about"` |
| `/contacts` | `"contacts"` |
| `/contacts/{contact_id}` | `"contacts.contact_id"` |
| `/projects/{slug}/settings` | `"projects.slug.settings"` |
| `/a/b/c` | `"a.b.c"` |

Algorithm:

```python
def default_route_name(url_path: str) -> str:
    # "/" -> "index"; strip leading/trailing "/"
    segments = [s for s in url_path.strip("/").split("/") if s]
    if not segments:
        return "index"
    # Parameter segments: keep the param name, drop braces and type specifiers.
    # "{contact_id}" -> "contact_id"; "{id:int}" -> "id"
    cleaned = []
    for seg in segments:
        if seg.startswith("{") and seg.endswith("}"):
            inner = seg[1:-1]
            # "{name:type}" -> "name"
            name = inner.split(":", 1)[0]
            cleaned.append(name)
        else:
            cleaned.append(seg)
    return ".".join(cleaned)
```

**Rationale:**
- Predictable: a reader who knows the URL can always guess the name.
- No surprise suffixes (no `_get`/`_post` — methods stay implicit because `url_for` doesn't care about the method; POST routes use the same URL as GET routes in REST).
- Handles catch-all paths (`{path:path}` → `path`) without further special-casing.
- `"index"` for root is explicit; avoids generating an empty string for `/`.

**Rejected alternatives:**
- `contacts__contact_id__get` (underscore-separated + method suffix) — longer, no clearer, and method suffix is wrong: one route object often carries multiple methods (GET+POST).
- Opt-in only (`name=None` stays the default unless a user sets it) — solves the "name-at-all" problem but forces hand-editing across the app. Fails the original IA-refactor use case.
- Full file path (`pages.contacts.contact_id.page`) — leaks the on-disk structure into the name; renaming files would then also change names.

### 3.2 Opt-out / override

**Decision:** A page module may set a top-level `name = "..."` attribute to override the default.

```python
# pages/contacts/{contact_id}/page.py
name = "contact.detail"   # overrides default "contacts.contact_id"

def get(request): ...
```

**Rationale:**
- Same mechanism other page-level metadata uses (e.g., `actions`, `meta_provider`) — readable, discoverable by grep.
- No decorator needed (we don't have one for page handlers today).
- A user stuck with a legacy name from an older migration can keep it.

**Rejected alternative:** A `name` parameter on the `get`/`post` handlers themselves — ambiguous when a page has both GET and POST handlers; they should share a name.

### 3.3 Collision policy

**Decision:** Duplicate route names fail `app.check()` with a new `route_names` category at `Severity.ERROR` (and exit in debug mode, per the existing contract-check contract).

- Not a hard raise at freeze. Consistent with Invariant 1 of the parent plan: `app.check()` stays issue-first.
- Category is `"route_names"`, eligible for `app.override_contract_severity("route_names", ...)`.
- Error message lists all conflicting routes with their paths:

```
route_names: duplicate route name "contacts.detail" used by 3 routes:
  - GET  /contacts/{contact_id}         (from pages/contacts/{contact_id}/page.py)
  - GET  /customers/{customer_id}       (from pages/customers/{customer_id}/page.py)
  - POST /admin/contacts/{id}           (registered via @app.route, name="contacts.detail")
Rename one of them or set a module-level `name` attribute on the page files.
```

**Rejected alternative:** Last-wins — silent name clobbering that would make `url_for("x")` return an unpredictable URL depending on discovery order.

### 3.4 Fragment-variant routes

**Context:** The block-fetch dispatcher owns `/_frag/**` (`src/chirp/server/fragment_dispatch.py`). Fragment URLs are derived from a route's path + block name via `fragment_url(route_path, block_name)`. There isn't a separate route object per fragment variant — one route, many blocks.

**Decision:** Named routes name the underlying route, not each fragment variant. `url_for` (RFC 004) returns the user-facing URL only. If a user wants the fragment URL for a named route, they call `fragment_url(url_for("x"), "some_block")` — the two helpers compose.

**Rationale:** Fragment blocks are a template-level concern, not a routing concern. One name per route keeps the mental model flat.

---

## 4. Implementation Sketch

```python
# src/chirp/pages/discovery.py:585
route = PageRoute(
    url_path=url_path,
    ...
    name=default_route_name(url_path),   # was: name=None
    ...
)
# If the module sets a top-level `name`, override:
module_name = getattr(module, "name", None)
if isinstance(module_name, str) and module_name:
    route = dataclasses.replace(route, name=module_name)
```

```python
# src/chirp/app/registry.py:301 — page_wrapper path
self._state.pending_routes.append(
    PendingRoute(
        url_path,
        page_wrapper,
        methods,
        name=page_route.name,    # was: name=None
        referenced=False,
        page_source_handler=_handler,
    )
)
```

(Requires threading `name` through `register_page_handler`'s kwargs — one-line signature addition.)

```python
# After _compile_routes() in AppCompiler.freeze(), build the index:
def _build_routes_by_name(router: Router) -> Mapping[str, Route]:
    by_name: dict[str, Route] = {}
    duplicates: dict[str, list[Route]] = {}
    for route in router.routes:
        if route.name is None:
            continue
        if route.name in by_name:
            duplicates.setdefault(route.name, [by_name[route.name]]).append(route)
        else:
            by_name[route.name] = route
    # duplicates -> emit route_names ContractIssue via existing check infra
    return MappingProxyType(by_name)
```

---

## 5. Open Questions

- **OQ-1:** When the user sets module-level `name` but the derived default was already unique, do we emit an INFO-level contract issue noting the override? Recommend **no** — overrides are a first-class feature, not a smell.
- **OQ-2:** Should `/_frag/**` routes (the dispatcher itself) have a name? Recommend **no** — reserved prefix, not meant to be reverse-looked-up by users. The dispatcher registers with `name=None` today and stays that way.
- **OQ-3:** Do we namespace names by mount prefix when plugins mount a sub-tree? E.g., a plugin mounted at `/admin` with its own `contacts` page — is the name `contacts` or `admin.contacts`? Deferring: current `mount(plugin)` API doesn't have a clean seam for this; tackle alongside `mount_app` (RFC 005) if needed.

---

## 6. Acceptance Criteria for Sprint 2 Task 2.1

- `tests/test_page_discovery_names.py` covers:
  - `pages/page.py` → name `"index"`
  - `pages/contacts/page.py` → name `"contacts"`
  - `pages/contacts/{contact_id}/page.py` → name `"contacts.contact_id"`
  - `pages/projects/{slug}/settings/page.py` → name `"projects.slug.settings"`
  - Module-level `name = "override"` overrides default.
- `rg 'name=None' src/chirp/pages/discovery.py` returns zero hits in the `PageRoute(...)` constructor — the default now always flows.
- `app.check()` with two page.py files chosen to collide returns an ERROR issue in category `route_names`.
