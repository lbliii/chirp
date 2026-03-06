# Suspense + Layout Chain Support

**Status**: Implemented  
**Scope**: Chirp (chirp package)  
**Related**: dori collections page, mount_pages

---

## Problem

When a handler returns `Suspense` from a `mount_pages` route, the rendered output bypasses the layout chain entirely. The result is:

- **Missing shell**: No `<!DOCTYPE html>`, `<head>`, CSS links, or app shell (sidebar, navbar)
- **Unstyled content**: chirp-ui classes apply but no CSS is loaded
- **Inconsistent UX**: Other pages (Page, Template) get the full layout; Suspense pages do not

### Current Flow

```
Handler returns Suspense
    → upgrade_result() passes through unchanged (only Page → LayoutPage)
    → negotiate() matches Suspense
    → render_suspense(env, value, is_htmx=...)
    → template.render(shell_ctx)  # raw template, no layout
    → StreamingResponse(chunks)
```

### Desired Flow

```
Handler returns Suspense (from mount_pages route)
    → upgrade_result() wraps in LayoutSuspense (Suspense + layout_chain + context)
    → negotiate() matches LayoutSuspense
    → render_suspense(env, value, layout_chain=..., request=...)
    → page_html = template.render(shell_ctx)
    → shell_html = render_with_layouts(env, layout_chain, page_html, context, ...)
    → yield shell_html  # first chunk has full document
    → [OOB chunks unchanged]
```

---

## Code Analysis

### 1. `chirp/pages/resolve.py` — `upgrade_result`

**Current** (lines 126–161):

```python
def upgrade_result(result, cascade_ctx, layout_chain, context_providers) -> Any:
    if isinstance(result, Page):
        merged_ctx = {**cascade_ctx, **result.context}
        return LayoutPage(result.name, result.block_name, layout_chain=..., **merged_ctx)
    return result  # Suspense passes through
```

**Gap**: Suspense is returned unchanged. No layout metadata is attached.

---

### 2. `chirp/app/registry.py` — `page_wrapper`

**Current** (lines 168–174):

```python
async def page_wrapper(request: Request) -> Any:
    cascade_ctx = await build_cascade_context(...)
    kwargs = await resolve_kwargs(_handler, request, cascade_ctx, _service_providers)
    result = await invoke(_handler, **kwargs)
    return upgrade_result(result, cascade_ctx, _chain, _providers)
```

**Available at call site**: `_chain` (LayoutChain), `cascade_ctx`, `_providers`, `request`.

---

### 3. `chirp/server/negotiation.py` — `negotiate`

**Current** (lines 245–257):

```python
case Suspense():
    ...
    is_htmx = request is not None and request.is_fragment
    chunks = render_suspense(kida_env, value, is_htmx=is_htmx)
    return StreamingResponse(chunks=chunks, ...)
```

**Gap**: `render_suspense` receives only `env`, `value`, `is_htmx`. No `layout_chain`, `request`, or `context`.

---

### 4. `chirp/templating/suspense.py` — `render_suspense`

**Current** (lines 114–205):

- Phase 1: Split sync vs async context
- Phase 2: `yield template.render(shell_ctx)` — **no layout wrapping**
- Phase 3: Resolve awaitables
- Phase 4: `yield formatter(block_html, target_id)` for each deferred block

**Gap**: First chunk is raw template output. No integration with `render_with_layouts`.

---

### 5. `chirp/pages/renderer.py` — `render_with_layouts`

**Signature**:

```python
def render_with_layouts(
    env: Environment,
    *,
    layout_chain: LayoutChain,
    page_html: str,
    context: dict[str, Any],
    htmx_target: str | None = None,
    is_history_restore: bool = False,
) -> str:
```

**Behavior**: Wraps `page_html` in layout templates via `template.render_with_blocks({"content": page_html}, **context)`.

**Reusability**: Can be called from `render_suspense` with `page_html` = shell output.

---

### 6. `chirp/server/negotiation.py` — `_render_layout_page`

**Fragment handling** (lines 323–326):

```python
if is_fragment and not is_history_restore and not htmx_target:
    frag = Fragment(value.name, value.block_name, **value.context)
    return render_fragment(kida_env, frag)  # No layouts
```

**Implication**: For fragment requests (htmx swap, no target), we render just the block. Suspense should mirror this: when `is_fragment and not is_history_restore and not htmx_target`, skip layout wrapping for the first chunk.

---

## Proposed Design

### Option A: New `LayoutSuspense` Type (Recommended)

Introduce a wrapper type that carries Suspense + layout metadata. Negotiation dispatches on it before plain Suspense.

**Pros**: Clear separation, no mutation of Suspense, explicit in type system.  
**Cons**: One more type in the negotiation match.

### Option B: Extend `Suspense` with Optional Fields

Add `layout_chain: LayoutChain | None = None` and `request: Request | None = None` to Suspense.

**Pros**: Single type, handlers never construct it (upgrade_result sets it).  
**Cons**: Suspense dataclass grows; mixes "user return type" with "framework metadata."

### Option C: Wrapper in `upgrade_result` Only

`upgrade_result` returns a tuple or a small wrapper `(suspense, layout_chain, context)` that negotiate understands.

**Pros**: No new public type.  
**Cons**: Negotiation becomes more complex; tuple unpacking is fragile.

---

## Recommended Implementation (Option A)

### 1. Add `LayoutSuspense` in `chirp/templating/returns.py`

```python
@dataclass(frozen=True, slots=True)
class LayoutSuspense:
    """Suspense with layout chain — used when Suspense is returned from mount_pages."""

    suspense: Suspense
    layout_chain: LayoutChain
    context: dict[str, Any]  # merged cascade + suspense.context (sync only for shell)
    request: Request | None = None
```

### 2. Update `upgrade_result` in `chirp/pages/resolve.py`

```python
from chirp.templating.returns import LayoutPage, LayoutSuspense, Page, Suspense

def upgrade_result(...) -> Any:
    if isinstance(result, Page):
        ...
    if isinstance(result, Suspense) and layout_chain is not None and layout_chain.layouts:
        # Merge context (sync values only; awaitables stay in suspense.context)
        sync_ctx = {k: v for k, v in {**cascade_ctx, **result.context}.items()
                    if not inspect.isawaitable(v)}
        return LayoutSuspense(
            suspense=result,
            layout_chain=layout_chain,
            context=sync_ctx,
            request=None,  # Set by negotiator if available
        )
    return result
```

Note: `request` is not available in `upgrade_result` (only in the page_wrapper's closure). We have two choices:

- Pass `request` into `upgrade_result` (signature change), or
- Set `request` in the negotiator when we have a `LayoutSuspense` and need fragment detection.

The negotiator already has `request`. So we can either:
- Add `request` to the page_wrapper's `upgrade_result` call, or
- Have the negotiator pass `request` when calling `render_suspense` for `LayoutSuspense`.

Simpler: pass `request` into `upgrade_result` so `LayoutSuspense` is fully populated. That requires `page_wrapper` to pass `request`.

### 3. Update `page_wrapper` in `chirp/app/registry.py`

```python
return upgrade_result(result, cascade_ctx, _chain, _providers, request=request)
```

### 4. Update `upgrade_result` signature

```python
def upgrade_result(
    result: Any,
    cascade_ctx: dict[str, Any],
    layout_chain: LayoutChain | None,
    context_providers: tuple[ContextProvider, ...],
    request: Request | None = None,
) -> Any:
```

### 5. Update `negotiate` in `chirp/server/negotiation.py`

Add a case before `Suspense`:

```python
case LayoutSuspense():
    if kida_env is None:
        raise ConfigurationError(...)
    is_htmx = request is not None and request.is_fragment
    chunks = render_suspense(
        kida_env,
        value.suspense,
        is_htmx=is_htmx,
        layout_chain=value.layout_chain,
        context=value.context,
        request=value.request or request,
    )
    return StreamingResponse(chunks=chunks, ...)
case Suspense():
    # Existing path — no layouts
    ...
```

### 6. Update `render_suspense` in `chirp/templating/suspense.py`

```python
async def render_suspense(
    env: Environment,
    suspense: Suspense,
    *,
    is_htmx: bool = False,
    layout_chain: LayoutChain | None = None,
    context: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AsyncIterator[str]:
```

**Logic**:

1. Use `context` if provided; else `suspense.context`.
2. **First chunk (shell)**:
   - `page_html = template.render(shell_ctx)`
   - If `layout_chain` and layouts exist:
     - Determine if we should wrap (mirror `_render_layout_page`):
       - If `request` and `request.is_fragment` and not `request.is_history_restore` and not `request.htmx_target` → **no layout** (fragment)
       - Else → wrap: `page_html = render_with_layouts(env, layout_chain=layout_chain, page_html=page_html, context=shell_ctx, htmx_target=request.htmx_target if request else None, is_history_restore=request.is_history_restore if request else False)`
   - `yield page_html`
3. **OOB chunks**: Unchanged. Block targets live inside the page content; layout wrapping does not affect them.

### 7. Imports and Exports

- `chirp/templating/returns.py`: Add `LayoutSuspense`, export it.
- `chirp/__init__.py`: Export `LayoutSuspense` if we want it public (likely not; it's internal).
- `chirp/pages/resolve.py`: Import `inspect` for `isawaitable` check.

---

## Edge Cases

### 1. Fragment Requests

When `is_fragment and not is_history_restore and not htmx_target`, do not wrap in layouts. Same as `LayoutPage`.

### 2. History Restore

When `is_history_restore`, wrap with full layout chain.

### 3. HX-Target Present

Use `layout_chain.find_start_index_for_target(htmx_target)` to compute layout depth, same as `render_with_layouts`.

### 4. No Layouts

If `layout_chain` is `None` or `layout_chain.layouts` is empty, skip wrapping. Fall back to current behavior.

### 5. Sync-Only Suspense

When there are no awaitables, `render_suspense` yields one chunk. That chunk should also be layout-wrapped when `layout_chain` is provided.

---

## Testing

### Unit Tests (`chirp/tests/test_suspense.py`)

- Add `test_layout_suspense_wraps_shell_in_layouts` — use a minimal layout template, assert first chunk contains layout HTML.
- Add `test_layout_suspense_fragment_request_skips_layouts` — when `request.is_fragment` and no target, first chunk has no layout.
- Add `test_layout_suspense_oob_targets_unchanged` — OOB chunks still target correct IDs.

### Integration (dori)

- Revert collections page to `Suspense` (from current `Page` workaround).
- Verify `/collections` renders with full shell, CSS, sidebar.

---

## Migration

- **Backward compatible**: Handlers that return `Suspense` from non–mount_pages routes continue to work (no `layout_chain` → no wrapping).
- **mount_pages + Suspense**: Automatically get layout wrapping via `LayoutSuspense`.

---

## Summary of File Changes

| File | Change |
|------|--------|
| `chirp/templating/returns.py` | Add `LayoutSuspense` dataclass |
| `chirp/pages/resolve.py` | Extend `upgrade_result` to wrap Suspense in LayoutSuspense when layout_chain present; add `request` param |
| `chirp/app/registry.py` | Pass `request` to `upgrade_result` |
| `chirp/server/negotiation.py` | Add `LayoutSuspense` case; pass layout params to `render_suspense` |
| `chirp/templating/suspense.py` | Add `layout_chain`, `context`, `request` params; wrap first chunk when appropriate |
| `chirp/tests/test_suspense.py` | Add layout integration tests |

---

## Alternative: Simpler Approach

If we want to avoid a new type, we could have `upgrade_result` attach layout metadata to the Suspense by returning a wrapper that `negotiate` recognizes. For example, a private `_LayoutSuspense` that is a `Suspense` subclass or a simple wrapper object. The negotiator would check `hasattr(value, 'layout_chain')` or `isinstance(value, LayoutSuspense)`. The cleanest remains a dedicated `LayoutSuspense` type with an explicit `negotiate` case.
