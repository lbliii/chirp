# RFC 019: Live-preserving template reload

**Status:** Accepted — offline planner foundation implemented; browser patching
and continuity canary pending

**Issue:** [#341](https://github.com/lbliii/chirp/issues/341)

**Last audited:** 2026-07-09

**Shipping impact:** None. The internal planner is not wired into the reload
channel. This RFC does not change `AppConfig`, CLI behavior, template syntax,
render semantics, DevTools, or browser reload behavior.

## Summary

Chirp can make a narrow class of development template edits without replacing
the document or its persistent signal connection. The safe path is:

1. detect a changed Kida block by structural hash;
2. prove that the current page exposes a registered, live DOM target for that
   block;
3. re-request the current route through Chirp's existing htmx negotiation; and
4. let the selected htmx tier perform the swap and lifecycle processing.

Everything else falls back to today's full reload. A syntax error never becomes
an empty swap: the existing DOM stays visible and a debug diagnostic names the
template and error.

The first implementation must not hot-reload Python handlers, mutate the frozen
application graph, invent a parallel partial renderer, or replace an active
`/_chirp/live` connection.

## Current behavior

### Browser reload transport

`src/chirp/server/dev_browser_reload.py` currently provides a debug-only
`EventStream` at `GET /__chirp__/dev-reload`. Each browser connection polls
configured roots every 450 milliseconds and emits:

- `css` when only CSS changed; the browser cache-busts stylesheet links; or
- `reload` for HTML, Markdown, and mixed changes; the browser calls
  `location.reload()`.

The injected snippet is idempotent and stores its internal `EventSource` on
`window.__chirpDevReloadSource`. It is injected only into full-page responses,
never htmx fragments. `tests/test_dev_browser_reload.py` proves those
properties.

The debug route is classified as framework-owned and hidden by default in
`src/chirp/server/debug_runtime.py`, so DevTools does not confuse it with an
application `EventStream`.

### Template reload

`src/chirp/templating/integration.py` creates Kida's `Environment` with
`auto_reload=config.debug`. Kida checks a template's source hash when
`get_template()` observes a stale file, invalidates its compiled and analysis
caches, and compiles the new source.

That behavior updates the next render. It does not decide which live DOM region
is safe to replace.

### Process reload

Python changes remain owned by the existing Pounce development reload. Chirp
passes no browser asset suffixes to Pounce, so `.html`, `.css`, and `.md` do not
restart the process. This RFC does not change that boundary.

### Persistent signals

`signal_connect()` places one `/_chirp/live` connection around its sinks. Lucky
Cat deliberately keeps that wrapper outside `#main`, so ordinary boosted
`#main` swaps preserve the connection and htmx binds any new sinks beneath it.
That existing shell design is the continuity seam this RFC uses.

## Source audit receipts

### Kida block hashes

Kida 0.11's frozen `BlockMetadata` includes a deterministic `block_hash`, and
`Environment.get_template_structure()` returns a lightweight
`TemplateStructureManifest` with block names, hashes, inheritance, and context
dependencies.

A local two-block probe changed only block `a`:

```text
before: a=b472a18b5ebf9a8b  b=a876dbf3ac75acd5
after:  a=cc612db2f606918b  b=a876dbf3ac75acd5
```

This proves structural hashes can identify candidate blocks without rendering
user context. The hash is a change detector, not the patch payload.

The probe also found an important cache rule: a previously cached structure
manifest remains cached until `Environment.clear_template_cache([name])` is
called. An external watcher must invalidate the logical template name before it
reads the new manifest. Relying on `auto_reload` alone is insufficient for this
planner.

### Addressable fragments

`src/chirp/templating/fragment_target_registry.py` already maps stable DOM target
IDs to named fragment blocks. `src/chirp/server/fragment_dispatch.py` can invoke
an ordinary GET handler and extract a page block, while the normal `Page`
negotiation path selects registered targets from actual `HX-Target` metadata.

The normal route path is the stronger reload primitive because it preserves:

- middleware, authentication, and request-local context;
- the handler's authoritative data loading;
- `Page`/fragment negotiation and render intent;
- OOB siblings when the route legitimately emits them; and
- htmx lifecycle processing for Alpine, islands, focus, and new SSE sinks.

The watcher must never render a block from an empty or guessed context.

### OOB targets

`src/chirp/templating/oob_registry.py` maps named OOB blocks to target IDs and
swap strategies. Those mappings are useful proof of addressability, but they do
not by themselves provide the route context needed to render a fresh payload.
OOB-only layout regions therefore remain fallback-only until the planner can
prove a route-owned render path.

### Suspense snapshot

`src/chirp/templating/suspense.py` resolves the Kida template once before it
sends the shell and reuses that same object for deferred blocks. This is
internally consistent, but it creates a race with hot patching:

1. an old Suspense shell is visible;
2. a template edit hot-swaps a new block; and
3. an old in-flight deferred chunk arrives and overwrites it.

No revision marker currently lets the browser reject that stale chunk. An
active Suspense surface is therefore not eligible for live-preserving patching
in the first tier.

## Decision

Add a future debug-only template reload planner with three outcomes:

| Outcome | Browser action | When |
| --- | --- | --- |
| patch | htmx request/swap of one proven target | safe page block |
| diagnose | preserve DOM and show a visible debug error | compile/render failure |
| reload | current `location.reload()` behavior | unknown or unsafe change |

The existing full reload remains the universal fallback and the behavior until
a separately reviewed implementation ships.

The [maintainer decision for issue #341][issue-341-decision] approves only the
bounded planner and browser-canary phases described here. That approval does
not extend to a new renderer, public API, `AppConfig` or CLI surface, broader
dependency inference, or revision-aware Suspense changes. Those remain
separate design decisions.

### Implemented planner foundation

`src/chirp/templating/dev_template_reload.py` now provides the offline Phase 1
foundation:

- an immutable, source-backed inventory compiled from the frozen hypermedia
  program and fragment-target registry;
- explicit Kida cache invalidation followed by real manifest recompilation;
- separate changed, added, and removed block classification;
- redacted `patch`, `diagnose`, and `reload` plans with no HTML, context, or
  credentials;
- fail-closed route, target-count, connection-owner, shell, Suspense, safe-GET,
  and htmx-adapter gates; and
- a per-planner lock and monotonic revisions so concurrent edits cannot publish
  duplicate revision IDs.

The planner is intentionally not connected to `dev_browser_reload.py`. The
existing `reload`/`css` EventStream and full-document reload behavior are
unchanged. Real nested Kida blocks currently change ancestor hashes too, so
the planner conservatively selects `reload` when more than one block hash
changes. Authoritative ancestor pruning, browser DOM evidence, response
validation, DevTools records, and the five-edit Lucky Cat continuity canary
remain required before browser patching can ship.

## Change detection

### Logical template inventory

At freeze, debug wiring needs an immutable inventory of reachable logical
template names and their loader filenames. It should be derived from the same
compiled template surface used by contracts, not from a second broad directory
scan.

The inventory records:

- logical template name;
- source filename when the loader supplies one;
- block names and hashes;
- parent template name;
- route/template reachability; and
- registered fragment targets that can render each block.

It must not expose source text or user context to the browser.

### Invalidation order

For a changed file:

1. resolve it to one or more logical template names;
2. retain the old structure manifest;
3. call `clear_template_cache()` for those names;
4. compile and read the new manifest;
5. diff block hashes, names, inheritance, and top-level structure; and
6. classify the change before emitting a browser event.

Compilation errors stop before step 5 produces a patch. The previous DOM is not
cleared.

### Dependency closure

A direct block hash diff is sufficient only for a page template with no changed
composition boundary. Changes to imported macros, included templates,
components, parents, or layout files may affect consumers whose own local block
hash did not change.

Until Kida/Chirp can compile that dependency closure authoritatively, these
changes require full reload. A filesystem basename match or speculative grep is
not acceptable proof.

## Patch eligibility

A block is eligible only when every condition below is proven:

1. the changed logical template is reachable from the browser's current route;
2. exactly one registered fragment target maps to the changed block for that
   route/layout scope;
3. the target exists exactly once in the live document;
4. the target is below, not equal to or above, any `signal_connect()` owner;
5. replacing it cannot remove `<html>`, `<head>`, `<body>`, the DevTools boot,
   CSP/bootstrap scripts, or the application shell;
6. the current surface has no in-flight Suspense work for that target;
7. the route is safe to re-request as GET and returns a supported page/template
   surface;
8. the active htmx tier has a framework-owned request/swap adapter; and
9. the new response is non-empty and names the expected render intent.

Failure to prove any condition selects full reload. Eligibility is a safety
proof, not a best-effort optimization.

## Rendering the patch

The browser re-requests its current path and query using the selected target's
actual htmx request metadata. Chirp then invokes the real route, middleware, and
render plan. The result comes from the same template and named block as ordinary
navigation.

The browser must route the response through the frozen htmx tier's supported
swap path. Direct `innerHTML` assignment is rejected because it bypasses htmx
OOB processing, focus rules, Alpine initialization, island lifecycle events,
and SSE sink binding.

No new app-facing fragment endpoint or JSON representation is needed for the
first tier. Debug metadata may describe the plan, but HTML remains the payload.

## Signal safety

The connection owner is never a patch target. A page-content edit beneath the
owner may replace signal sinks; htmx must process the incoming fragment so those
sinks attach to the existing ancestor connection.

For Lucky Cat, the first canary edit should target page content inside `#main`.
The shell-level ticker remains outside that target, so the test proves its
`/_chirp/live` request stays open while the edited content appears.

Editing `_layout.html`, `signal_connect()`, the ticker's connection-owning shell
block, or an unknown component falls back to full reload. Live-preserving reload
does not mean every template edit is patchable.

## Suspense policy

The first implementation does not patch an active Suspense target. It either:

- waits until the browser proves all deferred chunks for that revision have
  completed; or
- falls back to full reload.

A later tier may add monotonically increasing render revisions to shells,
patches, and deferred chunks. The browser could then reject a chunk older than
the target's current revision. That change touches the Suspense render pipeline
and requires its own design review and end-to-end proof.

## Failure behavior

### Syntax or compile error

- keep the last valid DOM and active SSE connections;
- emit no patch HTML;
- show a debug-only overlay/toast naming the logical template, line when
  available, exception type, and repair action; and
- record the failed revision in DevTools.

The diagnostic clears only after a later valid compile. Production behavior is
unchanged.

### Empty or wrong response

An empty response, missing target, wrong render intent, or unexpected full
document is a trust failure. Do not swap it. Record the reason and use full
reload only when that reload can surface the error page; never erase the target
with empty HTML.

### Connection loss

If the reload channel itself disconnects, today's delayed full reload remains
the recovery behavior. The planner does not monkey-patch global `EventSource` or
application streams.

## DevTools

Each template edit should produce one redacted record:

```text
template: markets/page.html
changed blocks: movers, featured
decision: patch #main | reload | diagnose
reason: registered target | layout boundary | TemplateSyntaxError
revision: 17
```

The browser panel should also show whether the application signal connection
remained open across the edit. No rendered context, session key, CSRF token, or
HTML payload belongs in the trace record.

## Browser proof

The Lucky Cat Playwright canary must perform five valid edits to an eligible
page block and assert:

1. the edited marker appears after every save;
2. the same document remains loaded;
3. no second `/_chirp/live` request is opened;
4. the original signal request is not closed;
5. ticker events continue and the displayed value advances;
6. focus and scroll behavior follow the registered target policy;
7. htmx/Alpine/island lifecycle hooks run for replaced content; and
8. the reload planner records `patch`, not `reload`.

A sixth edit introduces invalid Kida syntax and asserts the old content remains,
the ticker continues, and a visible diagnostic appears. Fixing the syntax must
clear the diagnostic and apply the next valid revision.

Separate tests cover layout edits and active Suspense, both of which must select
the documented fallback.

## Concurrency and lifecycle

The template inventory is immutable after freeze. Per-browser revision and
eligibility state belongs to that browser's debug reload connection. If file
scanning is later shared across tabs, its mutable publication state requires an
explicit lock and app-lifespan shutdown; this RFC does not assume a global
unlocked watcher.

Concurrent saves are coalesced by filename, but revisions stay monotonic. A
client must never apply revision 12 after revision 13. Failed revisions remain
observable and cannot silently reuse a prior success identifier.

## Compatibility

- Debug mode only; production gets no watcher, endpoint, script, or trace.
- No JavaScript build pipeline or client-side state store.
- Htmx 2 and htmx 4 use version-owned adapters selected from the frozen
  manifest. The RFC does not guess a future htmx 4 API.
- Pages without htmx provisioning use full reload.
- Python changes remain process reloads.
- CSS keeps the current link cache-bust path.
- Markdown and unknown assets keep full reload unless a later compiler maps
  them to an exact render surface.

## Rollout

### Phase 0: current RFC

- record the source audit and block-hash probe;
- define conservative eligibility and failure behavior; and
- ship no behavior change.

### Phase 1: planner without browser mutation — foundation implemented

- compile the debug-only logical template inventory — helper implemented;
- classify real edits as patch, diagnose, or reload — implemented and tested;
- expose decisions in DevTools while still performing full reload — pending;
  and
- measure false patch eligibility against Forum Shell and Lucky Cat — nested
  ancestor-hash fallback recorded; broader measurement pending.

This phase touches compiler/debug wiring and requires a separate implementation
review.

### Phase 2: eligible page-target patches

- add the htmx-tier adapter;
- patch only registered page targets;
- keep layout/import/component/Suspense changes on full reload; and
- run the five-edit Lucky Cat continuity canary.

### Phase 3: broader dependency and revision model

- compile imported/included/component dependency closure;
- add a reviewed Suspense revision protocol if justified; and
- expand eligibility only when contract and browser proof stay fail-loud.

## Required implementation proof

1. Kida manifest invalidation observes only the changed block hash in a
   two-block fixture.
2. Changed, added, and removed blocks are classified separately.
3. A syntax error produces no patch payload and preserves the DOM.
4. A registered target re-renders through the real route and middleware.
5. An unregistered, duplicate, layout-owning, or connection-owning target falls
   back to full reload.
6. Empty and full-document responses never replace a narrow target.
7. Htmx lifecycle proof covers OOB, Alpine, islands, focus, and signal sinks.
8. Active Suspense selects fallback until revision-aware chunks exist.
9. Five Lucky Cat edits preserve one continuously updating signal connection.
10. Debug-disabled and production apps expose none of the new machinery.
11. Concurrent edits cannot reorder applied revisions.
12. Public-safe traces contain no context values, credentials, or HTML payloads.

## Rejected alternatives

### Render changed blocks with empty context

Rejected because visible HTML would be incomplete or wrong. The real route owns
context construction.

### Hash rendered output

Rejected as the primary detector because rendering needs request/user context,
may execute expensive work, and can be nondeterministic. Structural hashes
select candidates; the normal route produces payloads.

### Patch every block whose hash changed

Rejected because named blocks are render units, not automatically live DOM
targets. Addressability and connection ownership must be proven.

### Replace the whole shell with OOB

Rejected because replacing a signal connection owner defeats the feature and
drops live state.

### Direct DOM `innerHTML`

Rejected because it bypasses htmx and extension lifecycle behavior.

### Hot-reload Python handlers in place

Rejected because setup registries, frozen state, imports, and lifecycle hooks
cannot be safely mutated piecemeal. Pounce process reload remains authoritative.

## Non-goals

- production template mutation;
- universal patchability for every template edit;
- Python handler/module hot replacement;
- a new public `AppConfig` field in this RFC;
- a new CLI flag;
- a parallel partial-template system;
- a JSON application rendering path; or
- changes to OOB, Suspense, signal, or return-type semantics.

## Collateral

No changelog: internal planner foundation only, with no shipped browser
behavior. Site, example, scaffold, public API, migration, and release
collateral wait for browser integration.

[issue-341-decision]: https://github.com/lbliii/chirp/issues/341#issuecomment-4929173683
