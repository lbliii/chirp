# Epic: Reactive System Phase 2 — Scoped Streams & Connection Awareness

**Status**: Implemented, awaiting product-scale validation
**Updated**: 2026-05-09 - `ConnectionInfo`, audience filtering, presence, inverse dependency lookup, reactive contract checks, and the `reactive_tasks` example are present. Remaining roadmap work is docs/example parity and validation in a real app, not the original framework build.
**Created**: 2026-04-12
**Target**: 0.5.0
**Estimated Effort**: 30–45h (Sprints 0–4)
**Dependencies**: None — ReactiveBus, DependencyIndex, reactive_stream() shipped in 0.4.0
**Source**: Codebase audit of reactive system (bus.py, index.py, stream.py, events.py); PBP forum plan identifies per-room SSE scoping and presence as blockers for production use.

---

## Why This Matters

The reactive system shipped in 0.4.0 works for single-document, small-user-count scenarios but cannot support production multi-user applications because it broadcasts all events to all subscribers of a scope with no filtering, no presence awareness, and no wire optimization.

1. **No per-connection filtering** — `ReactiveBus.emit_sync()` (bus.py:49) broadcasts to ALL subscribers of a scope. If 50 users watch the same forum thread, changing user A's draft re-renders for all 50. The only filter is `origin` echo-cancellation (stream.py:62-63), which prevents self-echo but not cross-user noise.
2. **No presence system** — No way to know who's connected to a scope. Can't show "3 users viewing this thread" or detect stale connections. Bus only exposes aggregate `subscriber_count` (bus.py:125-128), not per-scope identity.
3. **Full context rebuild per event** — `reactive_stream()` (stream.py:73) calls `context_builder()` on every event regardless of which paths changed. A 1-character edit triggers a full database query and full block re-render for every affected subscriber.
4. **No disconnect notification** — Bus cleanup relies on async generator `finally` (bus.py:78-84). The app never learns when a subscriber disconnects, so per-connection state (presence, cursors) can't be cleaned up.
5. **Manual unsafe registration** — The example app (reactive_tasks/app.py:100) directly mutates internal dicts: `dep_index._path_to_blocks.setdefault(...)`. No public registration API validates block existence at registration time.

The PBP forum — Chirp's first production downstream — needs per-thread SSE scoping, presence indicators, and efficient updates. Without this work, the forum would either burn bandwidth broadcasting to all users or require an entirely custom SSE layer outside the framework.

### Evidence Table

| Layer/Source | Key Finding | Proposal Impact |
|-------------|-------------|-----------------|
| bus.py:49 | `emit_sync()` broadcasts to ALL subscribers of scope | FIXES — Sprint 2 adds subscriber metadata + filtered emit |
| stream.py:73 | `context_builder()` called on every event, ignores `changed_paths` | FIXES — Sprint 3 passes changed_paths to context builder |
| bus.py:78-84 | Unsubscribe only via generator exit, no callback | FIXES — Sprint 2 adds `on_disconnect` callback |
| bus.py:125-128 | Only aggregate subscriber_count, no per-scope identity | FIXES — Sprint 2 adds presence tracking |
| reactive_tasks/app.py:100 | Direct `_path_to_blocks` dict mutation | FIXES — Sprint 1 adds public registration API |
| events.py | No presence event type | FIXES — Sprint 2 adds PresenceEvent |
| stream.py:62-63 | Origin filtering is echo-only, not per-user routing | FIXES — Sprint 2 adds connection metadata |
| index.py | No inverse mapping (block → paths) | FIXES — Sprint 3 adds `block_dependencies()` |
| rules_reactive.py | No per-scope bottleneck warnings | MITIGATES — Sprint 4 adds contract checks |
| PBP forum plan | Per-thread SSE scoping identified as blocker | FIXES — Sprint 2 is purpose-built for this |

### Invariants

These must remain true throughout or we stop and reassess:

1. **Backward compatible**: Existing `reactive_stream()` callers (no metadata, no filtering) must work unchanged. New features are opt-in via keyword arguments. `uv run pytest tests/test_reactive_*.py` passes at every sprint.
2. **Thread-safe**: All new mutable state uses `threading.Lock` (not asyncio locks). `emit_sync()` remains callable from any thread. Concurrency stress tests (tests/test_concurrency/) pass.
3. **No framework patches for the forum**: All reactive Phase 2 features ship in chirp proper. The PBP forum consumes them as a downstream app, never forking.
4. **Tests cover every new code path**: Every new public method has at least one unit test and one integration test. No sprint ships without `uv run pytest` green.

---

## Target Architecture

After Phase 2, the reactive system supports:

```python
# 1. Safe public registration (Sprint 1)
index = DependencyIndex()
index.register("tasks", BlockRef("board.html", "task_list"))        # validates block exists
index.register("tasks", BlockRef("board.html", "task_count", dom_id="count"))
index.derive("tasks.stats", from_paths={"tasks"})

# 2. Connection-aware subscriptions (Sprint 2)
async def events(request: Request):
    return reactive_stream(
        bus, scope=f"thread-{thread_id}",
        index=index,
        context_builder=lambda paths: build_context(thread_id, paths),
        connection=ConnectionInfo(
            user_id=request.user.id,
            session_id=request.session.id,
        ),
    )

# 3. Filtered emit (Sprint 2)
bus.emit_sync(ChangeEvent(
    scope=f"thread-{thread_id}",
    changed_paths=frozenset({"posts"}),
    origin=session_id,
    # NEW: only notify users with these IDs (None = all)
    audience=frozenset({user_a.id, user_b.id}),
))

# 4. Presence (Sprint 2)
bus.presence(scope)  # -> {ConnectionInfo(...), ConnectionInfo(...)}

# 5. Optimized context (Sprint 3)
async def build_context(thread_id: str, changed_paths: frozenset[str]) -> dict:
    """Context builder now receives changed_paths for selective queries."""
    if "posts" in changed_paths:
        return {"posts": await fetch_posts(thread_id)}
    if "thread.meta" in changed_paths:
        return {"thread": await fetch_thread(thread_id)}
    return await fetch_all(thread_id)  # fallback
```

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|---------------------|
| 0 | Design: API surface, ConnectionInfo shape, presence semantics | 2–3h | Low | Yes (RFC only) |
| 1 | Safe registration API + `block_dependencies()` inverse map | 4–6h | Low | Yes |
| 2 | Connection metadata, filtered emit, presence tracking, disconnect callback | 10–14h | Medium | Yes |
| 3 | Changed-paths passthrough to context builder + selective rendering | 8–12h | Medium | Yes |
| 4 | Contract checks for reactive patterns + reactive_tasks example upgrade | 4–6h | Low | Yes |

---

## Sprint 0: Design & Validate

**Goal**: Settle API decisions on paper before touching code.

### Task 0.1 — ConnectionInfo shape

Decide frozen dataclass fields: `user_id: str | None`, `session_id: str`, `metadata: dict[str, str]` (extensible). Decide whether metadata is typed or freeform.

**Acceptance**: Written decision in this plan's changelog. At least 2 usage examples (forum thread, collaborative document).

### Task 0.2 — Presence semantics

Decide: Does presence track `ConnectionInfo` objects or just counts? How is disconnect detected — generator exit only, or heartbeat timeout? What event does the bus emit on join/leave?

**Acceptance**: Written decision. Edge cases documented: browser tab close, network drop, duplicate connections from same user.

### Task 0.3 — Audience filtering design

Decide: Is `audience` on `ChangeEvent` (per-event) or on subscription (per-connection)? Per-event is more flexible but requires emitter to know recipient IDs. Per-connection is simpler but less dynamic.

**Acceptance**: Written decision with trade-off analysis.

---

## Sprint 1: Safe Registration API + Inverse Map

**Goal**: Replace direct dict mutation with a validated public API and add block→path lookups.

### Task 1.1 — `DependencyIndex.register()` public method

Add `register(path: str, block: BlockRef) -> None` to `DependencyIndex`. Validates that `block` has non-empty `template_name` and `block_name`. Replaces direct `_path_to_blocks` access.

**Files**: `src/chirp/pages/reactive/index.py`
**Acceptance**: `rg '_path_to_blocks\[' examples/` returns zero hits. `uv run pytest tests/test_reactive_*.py` passes.

### Task 1.2 — `block_dependencies()` inverse query

Add `block_dependencies(template_name: str, block_name: str) -> frozenset[str]` to `DependencyIndex`. Returns all paths that a given block depends on.

**Files**: `src/chirp/pages/reactive/index.py`
**Acceptance**: Test: register block A on paths {"x", "y"}, `block_dependencies("tmpl", "A")` returns `frozenset({"x", "y"})`.

### Task 1.3 — Update reactive_tasks example

Replace `dep_index._path_to_blocks.setdefault(...)` with `dep_index.register(...)`.

**Files**: `examples/standalone/reactive_tasks/app.py`
**Acceptance**: Example starts and passes its test suite.

### Task 1.4 — Tests

- `register()` with valid/invalid BlockRef
- `block_dependencies()` with direct, derived, and prefix paths
- Backward compat: `register_template()` and `register_from_sse_swaps()` still work

**Files**: `tests/test_reactive_index.py` (new or extended)

---

## Sprint 2: Connection Metadata, Filtered Emit, Presence

**Goal**: Make the bus connection-aware so apps can filter events per-user and track who's online.

### Task 2.1 — ConnectionInfo dataclass

Create `ConnectionInfo` frozen dataclass in `events.py`: `user_id: str | None`, `session_id: str`, `connected_at: float` (monotonic), `metadata: dict[str, str]`.

**Files**: `src/chirp/pages/reactive/events.py`
**Acceptance**: `from chirp.pages.reactive import ConnectionInfo` works.

### Task 2.2 — Connection-aware subscribe

Extend `ReactiveBus.subscribe(scope, connection: ConnectionInfo | None = None)` to store connection info alongside queue. Internal mapping: `_subscribers: dict[str, dict[asyncio.Queue, ConnectionInfo | None]]`.

**Files**: `src/chirp/pages/reactive/bus.py`
**Acceptance**: Existing tests pass (connection=None is backward compatible). New test: subscribe with ConnectionInfo, verify it's stored.

### Task 2.3 — Filtered emit via audience

Add `audience: frozenset[str] | None` to `ChangeEvent`. When set, `emit_sync()` only enqueues to subscribers whose `connection.user_id` is in `audience`. `None` = broadcast to all (current behavior).

**Files**: `src/chirp/pages/reactive/events.py`, `bus.py`
**Acceptance**: Test: 3 subscribers (users A, B, C), emit with `audience={"A", "B"}`, only A and B receive event.

### Task 2.4 — Presence API

Add `ReactiveBus.presence(scope: str) -> frozenset[ConnectionInfo]` returning all active connections for a scope. Add `on_disconnect` callback parameter to `subscribe()`.

**Files**: `src/chirp/pages/reactive/bus.py`
**Acceptance**: Test: 2 subscribers, `presence()` returns 2 ConnectionInfo. One unsubscribes, `presence()` returns 1. `on_disconnect` callback fired.

### Task 2.5 — Wire into reactive_stream()

Add `connection: ConnectionInfo | None = None` parameter to `reactive_stream()`. Pass to `bus.subscribe()`.

**Files**: `src/chirp/pages/reactive/stream.py`
**Acceptance**: Existing tests pass. New test: `reactive_stream()` with ConnectionInfo, audience-filtered event only delivered to matching connection.

### Task 2.6 — Tests

- Audience filtering: subset, empty, None (broadcast)
- Presence: join, leave, duplicate user, scope isolation
- Disconnect callback: normal exit, exception exit
- Thread safety: concurrent subscribe/emit/presence
- Backward compat: all existing tests still pass

---

## Sprint 3: Changed-Paths Passthrough & Selective Context

**Goal**: Stop rebuilding full context on every event. Pass `changed_paths` to context builder so apps can query selectively.

### Task 3.1 — Context builder signature change

`reactive_stream()` now calls `context_builder(changed_paths)` instead of `context_builder()`. Detect arity via `inspect.signature` — if builder accepts 0 args, call without args (backward compat). If 1 arg, pass `frozenset[str]`.

**Files**: `src/chirp/pages/reactive/stream.py`
**Acceptance**: Existing 0-arg context builders still work. New test: 1-arg builder receives correct `changed_paths`.

### Task 3.2 — Selective rendering guidance

When `block_dependencies()` is available and context builder returns partial context, only yield Fragment for blocks whose dependencies overlap with `changed_paths`. Skip blocks that don't depend on any changed path.

**Files**: `src/chirp/pages/reactive/stream.py`
**Acceptance**: Test: 3 blocks, paths A/B/C. Change path A → only block depending on A is yielded.

### Task 3.3 — Tests

- 0-arg builder backward compat
- 1-arg builder receives changed_paths
- Partial context: missing keys for unaffected blocks don't cause errors
- Derivation expansion: changing source path X expands to derived paths, all affected blocks rendered

---

## Sprint 4: Contract Checks + Example Upgrade

**Goal**: Catch reactive misconfigurations at startup and prove the full API with an upgraded example.

### Task 4.1 — Contract check: audience without ConnectionInfo

Warn if any route uses `reactive_stream()` without passing `connection` but the app emits events with `audience`. Static analysis may be limited; consider a runtime check at first emit.

**Files**: `src/chirp/contracts/rules_reactive.py`
**Acceptance**: Test: app emits with audience but stream has no ConnectionInfo → WARNING.

### Task 4.2 — Contract check: unregistered paths in emit

Warn if `ChangeEvent.changed_paths` contains paths not registered in any DependencyIndex.

**Files**: `src/chirp/contracts/rules_reactive.py`
**Acceptance**: Test: emit event with path "nonexistent" → WARNING at check time (requires path registry).

### Task 4.3 — Upgrade reactive_tasks example

Add presence indicator ("N users watching"), audience-filtered notifications, and selective context builder to the reactive_tasks example.

**Files**: `examples/standalone/reactive_tasks/`
**Acceptance**: Example runs, shows presence count, selective updates work.

### Task 4.4 — Export from chirp public API

Ensure `ConnectionInfo`, `PresenceEvent` (if added), and `DependencyIndex.register()` are exported from `chirp.pages.reactive.__init__`.

**Acceptance**: `from chirp.pages.reactive import ConnectionInfo, ReactiveBus, DependencyIndex` works.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Audience filtering adds latency to emit_sync() (iterating subscribers) | Medium | Low | Filtering is O(N) where N = subscribers per scope. For <1000 subscribers this is sub-millisecond. Profile in Sprint 2 stress tests. |
| Context builder signature detection via inspect is fragile | Low | Medium | Use try/except on call: try 1-arg first, fall back to 0-arg. Avoids inspect entirely. (Sprint 3, Task 3.1) |
| Presence tracking leaks memory on long-running scopes | Medium | Medium | Scope cleanup in `close(scope)` already deletes subscriber sets. Presence piggybacks on same cleanup. Add test for 1000 subscribe/unsubscribe cycles. (Sprint 2, Task 2.4) |
| Backward-incompatible ChangeEvent if audience field added | Low | High | `audience` defaults to `None` (broadcast). Existing code never sets it. Frozen dataclass with default = safe. (Sprint 2, Task 2.3) |
| Per-connection state doubles memory per subscriber | Low | Low | ConnectionInfo is a small frozen dataclass (~5 fields). 10,000 connections = ~1MB. Acceptable. |

---

## Success Metrics

| Metric | Current (0.4.0) | After Sprint 2 | After Sprint 4 |
|--------|-----------------|----------------|-----------------|
| Public registration API calls in examples | 0 (direct dict access) | 0 (Sprint 1 fixes) | All examples use `register()` |
| Per-user event filtering | None | Audience-based filtering | + contract warnings |
| Presence tracking | None (aggregate count only) | Per-scope ConnectionInfo sets | + example UI |
| Context builder efficiency | Full rebuild every event | Full rebuild every event | Selective via changed_paths |
| Reactive module LOC | 790 | ~950 | ~1100 |
| Reactive test LOC | ~1000 | ~1400 | ~1600 |

---

## Relationship to Existing Work

- **PBP Forum MVP** (`plan/drafted/epic-pbp-forum-mvp.md`) — prerequisite — Sprint 3 of the forum plan ("scope SSE to threads") depends on per-scope filtering and presence from this epic's Sprint 2.
- **Contract Extensions** (`plan/drafted/rfc-contract-extensions.md`) — parallel — Phase 4 (component call validation) is blocked on Kida, unrelated to reactive work. Phases 1-3 already shipped.
- **Accessibility Contracts** (`plan/completed/epic-accessibility-contracts.md`) — complete — no dependency.
- **Pagination** (`plan/completed/rfc-pagination.md`) — complete — no dependency, but forum will use both pagination and reactive together.

---

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-04-12 | Initial draft | Evidence-driven plan from reactive system codebase audit |
