# RFC: Shared Store for Multi-Consumer Deferred Data

**Status**: Open - Phase 1 server-side deferred cache is the next actionable slice  
**Updated**: 2026-05-09 - no `chirp.stores` or `cached_deferred` implementation exists; keep Alpine store and SSE broadcast phases deferred until server-side cache semantics are proven.  
**Date**: 2026-04-11  
**Scope**: `src/chirp/templating/suspense.py`, new `src/chirp/stores/` module (proposed)  
**Related**: Suspense renderer, `defer_blocks` parameter, Alpine.js injection

---

## Problem

A single deferred data source (e.g. GitHub star count, user profile, notification count) is consumed by multiple independent page regions. Today each region gets its own Suspense block re-render, and each page navigation triggers fresh API calls.

### Concrete example

The b-site home page shows a GitHub star badge in two places: the hero section and a lower blade. Both depend on `github_stars_bengal`, which is an async call to the GitHub API.

```python
return Suspense("page.html",
    github_stars_bengal=fetch_github_stars_label("lbliii", "bengal"),
    github_stars_chirp=fetch_github_stars_label("lbliii", "chirp"),
    # ... four more repos
)
```

**Issues today:**

1. **Duplicate work** — Suspense re-renders both `hero_stars` and `blade_stars` blocks. With parent-block pruning (just landed), at least the ancestor blocks are skipped, but the resolved value is still rendered twice from the same source.

2. **No navigation persistence** — boosted htmx navigation triggers a fresh `Suspense` render with new API calls. The star count fetched 2 seconds ago is discarded. Users see skeletons flash on every page transition.

3. **No cross-page sharing** — the `/stack` page also shows star counts for the same repos. Each page makes independent API calls to the same endpoints.

4. **No real-time updates** — if the star count changes, every badge showing it is stale until the next full navigation.

---

## Design Goals

| Goal | Priority |
|------|----------|
| Fetch once per key, propagate to N consumers | Must |
| Survive boosted navigation (no re-fetch) | Must |
| TTL-based invalidation | Must |
| Work without Alpine (SSR-only fallback) | Must |
| Real-time push (SSE) | Nice to have |
| Type-safe store keys | Nice to have |

---

## Options

### Option A: Server-side TTL cache (minimal)

Cache resolved values in a server-side `dict[str, CachedValue]` with TTL expiry. Suspense resolves from cache when available, falls back to the real data source when expired.

```python
from chirp.stores import cached_deferred

return Suspense("page.html",
    github_stars_bengal=cached_deferred(
        "gh:lbliii/bengal",
        fetch_github_stars_label("lbliii", "bengal"),
        ttl=300,
    ),
)
```

**How it works:**
- `cached_deferred()` returns the cached value (sync) if fresh, or the awaitable if stale
- Suspense treats a sync value as immediate (no skeleton), an awaitable as deferred
- Cache is a module-level `threading.Lock`-protected dict (3.14t safe)

**Pros:** Zero client-side changes. No Alpine dependency. Works with existing Suspense.  
**Cons:** No navigation persistence (each page load checks cache, but boosted navigations still re-render). Doesn't solve the "N consumers" structural issue — still re-renders each block.

**Complexity:** Low — ~50 lines of new code.

### Option B: Alpine.store + JSON bridge (client persistence)

Push resolved values to an Alpine.js store on the client. Subsequent navigations read from the store instead of waiting for Suspense.

```python
return Suspense("page.html",
    github_stars_bengal=fetch_github_stars_label("lbliii", "bengal"),
    store_keys={"github_stars_bengal": "gh.bengal_stars"},
)
```

Suspense OOB chunks include a `<script>` tag that writes to `Alpine.store`:

```html
<script>Alpine.store('gh').bengal_stars = "42";</script>
```

Template reads from the store on subsequent navigations:

```kida
<span x-text="$store.gh.bengal_stars || 'Loading...'"></span>
```

**Pros:** Survives boosted navigation. Single source of truth on client. Alpine already loaded.  
**Cons:** Requires Alpine (breaks SSR-only fallback). Template syntax changes. Client/server contract for store keys. Two rendering paths (server for initial, Alpine for subsequent).

**Complexity:** Medium — store registration, OOB script injection, template helpers.

### Option C: SSE broadcast store (real-time)

Dedicated `EventStream` that pushes store updates to all connected clients. Combines server-side caching (Option A) with client-side persistence (Option B) and adds real-time push.

```python
@app.route("/store/events")
def store_events():
    return EventStream(store.subscribe())

# In page handler:
store.set("gh.bengal_stars", await fetch_github_stars_label(...), ttl=300)
```

Client subscribes via htmx SSE:

```html
<div hx-ext="sse" sse-connect="/store/events">
  <span sse-swap="gh.bengal_stars"></span>
</div>
```

**Pros:** Real-time. Works across pages. Minimal template changes.  
**Cons:** Persistent SSE connection per client. Server memory for subscriber registry. Most complex option. Overkill for mostly-static data like star counts.

**Complexity:** High — subscriber management, reconnection, cleanup.

---

## Recommendation

**Phase 1: Option A (server cache).** Solve the immediate cost problem — no duplicate API calls within the TTL window. This is a 50-line utility that works with existing Suspense and requires no template changes.

**Phase 2: Option B (Alpine store).** Add client-side persistence for data that should survive boosted navigation. This builds on Phase 1 (cache feeds the store on first load; store avoids re-fetch on navigation). Only needed for high-frequency navigation patterns.

**Phase 3: Option C (SSE broadcast).** Only pursue if real-time updates become a requirement. The EventStream infrastructure already exists in Chirp; the missing piece is a server-side pub/sub registry.

### Phase 1 API sketch

```python
# chirp/stores/cache.py

@dataclass(frozen=True, slots=True)
class CachedValue:
    value: object
    expires_at: float

class DeferredCache:
    def __init__(self) -> None:
        self._data: dict[str, CachedValue] = {}
        self._lock = threading.Lock()

    def get_or_defer(
        self,
        key: str,
        factory: Callable[[], Awaitable[object]],
        ttl: float = 300,
    ) -> object | Awaitable[object]:
        """Return cached value if fresh, otherwise return the awaitable."""
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is not None and entry.expires_at > now:
                return entry.value

        async def _resolve() -> object:
            result = await factory()
            with self._lock:
                self._data[key] = CachedValue(result, time.monotonic() + ttl)
            return result

        return _resolve()
```

Usage in a page handler:

```python
from chirp.stores import DeferredCache

_stars_cache = DeferredCache()

def get(request):
    return Suspense("page.html",
        title="Home",
        github_stars_bengal=_stars_cache.get_or_defer(
            "gh:lbliii/bengal",
            lambda: fetch_github_stars_label("lbliii", "bengal"),
            ttl=300,
        ),
    )
```

When the cache is warm, `get_or_defer` returns the string directly (sync). Suspense sees a non-awaitable and includes it in the shell — no skeleton, no OOB chunk, no re-render.

---

## Open Questions

1. **Cache scope** — per-app singleton vs per-route instance? Singleton allows cross-page sharing but needs key namespacing.

2. **Eviction** — TTL-only or LRU? For small stores (< 100 keys), TTL is sufficient. LRU needed if the key space grows unbounded.

3. **Stampede protection** — when TTL expires, multiple concurrent requests all call the factory. Should `get_or_defer` hold a per-key lock to serialize? The `threading.Lock` protects the dict but not the factory call.

4. **Alpine store registration** — if Phase 2 proceeds, should Chirp auto-register `Alpine.store()` entries, or should templates declare them? Auto-registration is convenient but opaque.
