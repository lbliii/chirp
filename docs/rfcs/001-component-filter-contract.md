# RFC 001: Component Filter Contract — Loader/Filter Coherence

**Status:** Draft  
**Author:** (proposal)  
**Created:** 2025-03-04

---

## 1. Problem Statement

When using chirp-ui templates (e.g. `{% from "chirpui/forms.html" import key_value_form %}`), apps intermittently hit:

```
TemplateSyntaxError: Unknown filter 'html_attrs'. Did you mean 'xmlattr'?
  Location: chirpui/forms.html:17
```

The failure is intermittent—often after hot reload or "making a change"—and sometimes requires a hard restart to resolve. This RFC analyzes the root cause and proposes a long-term design.

---

## 2. Deep Dive: Current Architecture

### 2.1 Data Flow

```
App creation (mutable)
    │
    ├── use_chirp_ui(app)        → StaticFiles, middleware, [register_filters]
    ├── chirp_ui.register_filters(app)  → app._template_filters["html_attrs"] = ...
    ├── app.template_filter("x")(fn)   → app._template_filters["x"] = ...
    │
    ▼
First request → _ensure_frozen() → AppCompiler.freeze()
    │
    ├── create_environment(config, template_filters, template_globals)
    │       │
    │       ├── Loaders: [FileSystemLoader(pages), ..., PackageLoader("chirp_ui", "templates")]
    │       ├── env.update_filters(BUILTIN_FILTERS)   ← chirp's built-ins
    │       └── env.update_filters(template_filters)   ← app's registered filters
    │
    └── kida_env stored in runtime_state
```

### 2.2 Filter Sources (Three Competing Sources)

| Source | When | Contains html_attrs? |
|--------|------|----------------------|
| **Chirp BUILTIN_FILTERS** | Always (create_environment) | Yes (chirp 0.1.4+); **No** (chirp 0.1.3?) |
| **App template_filters** | When app calls `chirp_ui.register_filters(app)` or `use_chirp_ui` (which now calls it) | Yes |
| **Chirp-ui PackageLoader** | When chirp_ui is importable | N/A — loader only; no filters |

### 2.3 The Design Gap

**Chirp** adds chirp-ui's `PackageLoader` in `create_environment` when `chirp_ui` is importable:

```python
# chirp/templating/integration.py:42-47
try:
    import chirp_ui
    loaders.append(PackageLoader("chirp_ui", "templates"))
except ImportError:
    pass
```

**Chirp does NOT add chirp-ui's filters** at that point. The filters come from:

1. Chirp's `BUILTIN_FILTERS` (if chirp version has them), or  
2. The app calling `chirp_ui.register_filters(app)` (or `use_chirp_ui` which now does it)

**Result:** Loader and filters are decoupled. Chirp makes chirp-ui templates *loadable* but does not guarantee the filters those templates *require* are present.

### 2.4 Why It Fails Intermittently

1. **Version mismatch:** Chirp 0.1.3 may not include `html_attrs` in `BUILTIN_FILTERS`. Chirp-ui templates assume it exists.

2. **Order/timing:** If the app forgets `register_filters`, or calls it after `freeze` (impossible but illustrates the contract), filters are missing.

3. **Hot reload:** On reload, import order or module re-execution can change which code path runs. If `use_chirp_ui` or `register_filters` is skipped or runs in a different order, the env may be built without chirp-ui filters.

4. **Two-phase setup:** Filters are registered at *app setup* (mutable phase). The env is built at *freeze* (first request). Any gap between "what the app registered" and "what gets passed to create_environment" causes failure.

---

## 3. Design Principle: Loader/Filter Coherence

**Principle:** If a template loader can load templates from a package, the environment must have the filters those templates require.

When Chirp adds `PackageLoader("chirp_ui", "templates")`, it is asserting that chirp-ui templates are valid for this environment. Therefore, the environment must have chirp-ui's required filters. The contract should be enforced at the point of loader registration, not delegated to app-level setup.

---

## 4. Proposed Long-Term Solution

### 4.1 Option A: Env-Level Fallback in create_environment (Recommended)

**Where:** `chirp/templating/integration.py` — `create_environment`

**What:** When chirp-ui's PackageLoader is added, ensure chirp-ui's required filters are present in the env as a *fallback* (only add if not already present).

```python
# After: env.update_filters(BUILTIN_FILTERS), env.update_filters(filters)

# When chirp-ui templates are loadable, ensure required filters exist.
# Fallback for older chirp or apps that didn't call register_filters.
try:
    import chirp_ui  # noqa: F401
    from chirp_ui.filters import bem, field_errors, html_attrs, validate_variant
    chirp_ui_filters = {
        "bem": bem,
        "field_errors": field_errors,
        "html_attrs": html_attrs,
        "validate_variant": validate_variant,
    }
    for name, fn in chirp_ui_filters.items():
        if name not in env.filters:
            env.update_filters({name: fn})
except ImportError:
    pass
```

**Pros:**
- Single source of truth: loader and filters are coupled at env creation
- Works regardless of chirp version, app setup, or hot reload
- No app code required
- User/app filters (from `template_filters`) are applied first, so overrides still work

**Cons:**
- Slight duplication: chirp_ui filters may be registered twice (once via app, once via fallback) — harmless
- Chirp depends on chirp_ui's filter API (but only when chirp_ui is importable)

### 4.2 Option B: Extensible Component Registry (Future-Proof)

**Where:** New abstraction in chirp

**What:** Define a protocol for "template components" that declare their loader + required filters:

```python
# Conceptual
class TemplateComponent(Protocol):
    def get_loader(self) -> BaseLoader: ...
    def get_required_filters(self) -> dict[str, Callable]: ...

# chirp_ui would implement this
# create_environment would iterate registered components
```

**Pros:** Scales to multiple component packages (chirp-ui, future libs)  
**Cons:** Heavier; chirp-ui is currently the only such package. YAGNI for now.

### 4.3 Option C: Keep use_chirp_ui Auto-Register (Current Band-Aid)

**What we did:** `use_chirp_ui` calls `chirp_ui.register_filters(app)`.

**Pros:** Simple, fixes most cases  
**Cons:** Only works when app calls `use_chirp_ui`. Fails if someone uses chirp-ui templates without it (e.g. custom loader, different static setup).

---

## 5. Recommendation

**Implement Option A** in `create_environment` as the long-term fix. This:

1. Enforces loader/filter coherence at the env level
2. Makes the environment self-consistent: loadable templates have their filters
3. Works with or without `use_chirp_ui` and `register_filters`
4. Is backward compatible: apps that already call `register_filters` get no behavior change (filters already present, fallback no-ops)

**Keep** the `use_chirp_ui` → `register_filters` change as defense-in-depth: it ensures filters are in the app's `template_filters` before freeze, which is the "normal" path. The env-level fallback handles edge cases (old chirp, forgotten calls, hot reload races).

---

## 6. Implementation Checklist

- [ ] Add env-level chirp-ui filter fallback in `create_environment`
- [ ] Add test: env has chirp-ui filters when chirp_ui is importable, even without `register_filters`
- [ ] Add test: user-registered filters override chirp-ui fallback
- [ ] Document the contract: chirp-ui templates require these filters; chirp guarantees them when chirp-ui is used
- [ ] Consider deprecating explicit `chirp_ui.register_filters(app)` in docs (optional; redundant but harmless)

---

## 7. References

- `chirp/templating/integration.py` — create_environment
- `chirp/templating/filters.py` — BUILTIN_FILTERS
- `chirp_ui/filters.py` — register_filters, html_attrs, bem, field_errors, validate_variant
- `chirp_ui/templates/chirpui/forms.html` — uses html_attrs, field_errors
- `chirp/ext/chirp_ui.py` — use_chirp_ui
