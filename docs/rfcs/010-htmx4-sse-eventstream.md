# RFC 010: htmx 4 SSE and Chirp `EventStream`

**Status:** Implemented for the explicit preview lane

**Issue:** [#550](https://github.com/lbliii/chirp/issues/550)

**Upstream preview:** htmx `4.0.0-beta5`, commit
[`5300af9e`](https://github.com/bigskysoftware/htmx/commit/5300af9e7af8b196f9fbf806cab79a5780b62291)

## Summary

Chirp will keep `EventStream` as its first-class post-load SSE return type and
will keep rendering updates from the same Kida template blocks. For htmx 4,
rendered updates travel as **unnamed** SSE messages through htmx's standard swap
pipeline. A targeted `Fragment` is wrapped after rendering in an
`<hx-partial>` that identifies the destination and swap strategy. Named SSE
events remain application DOM events and are never silently reinterpreted as
rendered swaps.

The version-aware `EventStream` formatter, native `sse_scope()` markup,
testing-helper parity, cache variation, DevTools metadata, and maintained
browser proof are implemented. The current htmx 2 wire and markup remain the
default until the htmx 4 preview lane is separately selected.

## Context

Chirp's htmx 2 integration relies on the `htmx-ext-sse` convention:

- `hx-ext="sse"` and `sse-connect` open an `EventSource`;
- `sse-swap="name"` listens for a named SSE event;
- `Fragment(target="name")` renders one named block and uses `name` as the
  `event:` field;
- signal names double as `event:` fields and `sse-swap` values.

htmx 4 deliberately changes that model. Its SSE extension uses `fetch()` and a
`ReadableStream`, intercepts `text/event-stream` in the normal request pipeline,
swaps unnamed messages as HTML, and dispatches named messages as DOM events.
`sse-swap` is removed. Persistent connections use `hx-sse:connect`. The
upstream details are documented in the
[htmx 4 SSE guide](https://four.htmx.org/extensions/hx-sse) and
[htmx 4 migration guide](https://four.htmx.org/migration-guide-htmx-4/).

That creates a semantic collision: Chirp currently uses a named event both as
an application event and as a rendered-target channel. The same frame cannot
mean both on htmx 4. Leaving the current format unchanged would turn every
targeted `Fragment` and every signal update into a DOM event with no swap.

## Goals

- Preserve `EventStream` and `SSEEvent` as the stable public transport types.
- Preserve one template and named blocks as the source of rendered HTML.
- Make rendered swaps and application DOM events unambiguous on the wire.
- Keep missing blocks, invalid targets, and empty rendered swaps fail-loud.
- Preserve one shared signal connection and one-to-many sinks.
- Preserve application-owned reconnect cursors from RFC 007.
- Keep the htmx 2 default behavior intact during the preview window.
- Give DevTools, `app.check()`, and testing helpers the same client-tier view.

## Non-goals

- No JSON event bus or browser state store.
- No WebSocket abstraction.
- No second partial-template system.
- No framework replay buffer or automatic event IDs.
- No new return type, `AppConfig` field, helper, or CLI flag in this RFC.
- No htmx 4 default flip; issue #551 owns that release decision.
- No implementation of signal markup or `EventStream` formatting here.

## Decision

### 1. Keep transport and rendered-update semantics separate

`SSEEvent` remains a literal SSE frame. When `event` is present, Chirp sends a
named event. htmx 4 dispatches it on the source element as a DOM event; it does
not swap the data. Chirp will not remove the event name or map it to a swap.

`Fragment` remains the typed rendered-update input. Chirp renders its named
block through the existing Kida surface, then selects a client-dialect envelope:

- htmx 2: the current named event contract;
- htmx 4: an unnamed message, with `<hx-partial>` for an explicit target;
- generic SSE clients: the current literal/raw behavior unless they explicitly
  opt into an htmx client dialect.

The envelope is transport metadata added after block rendering. It is not a
template, component serializer, or alternate render surface.

### 2. Select the dialect once at connection time

The connection captures one immutable SSE client dialect. It must not change
between messages.

The htmx 4 SSE extension sends `HX-Request-Type` and an `Accept` value that
includes `text/event-stream`. The htmx 2 `EventSource` path does not send
`HX-Request-Type`. The implementation may use those headers only in combination
with the explicitly provisioned client tier from issue #545. `Accept` alone is
not sufficient because generic SSE clients also request `text/event-stream`.

The selected dialect is carried privately from request negotiation to the SSE
formatter. It is not a new application-facing configuration surface.

### 3. Use htmx 4 connection markup explicitly

htmx 4 preview pages use version-matched scripts and:

```html
<div hx-sse:connect="/events">
  ...
</div>
```

They do not emit `hx-ext="sse"`, `sse-connect`, `sse-swap`, or
`hx-disinherit`. htmx 2 pages keep the current attributes while that tier is
supported. The two markup dialects must not be mixed on one connection.

The `htmx-2-compat` extension does not restore the removed `sse-swap` delivery
model. It cannot replace version-aware SSE formatting.

### 4. Unnamed HTML uses the normal swap pipeline

An unnamed htmx 4 message with ordinary HTML updates the connection's resolved
target using its normal `hx-target` and `hx-swap` context:

```text
data: <article id="latest">Rendered from a Chirp block</article>

```

This is appropriate for a `Fragment` without an explicit target and for
one-off streamed responses initiated by an ordinary `hx-get` or `hx-post`.

### 5. Targeted fragments use `<hx-partial>`

For htmx 4, `Fragment("dashboard.html", "stats", target="stats",
swap="innerHTML", ...)` becomes an unnamed frame whose data is:

```html
<hx-partial hx-target="#stats" hx-swap="innerHTML">
  <!-- rendered dashboard.html:stats block -->
</hx-partial>
```

For htmx 4, the target uses `Fragment.target`'s existing OOB-style DOM-ID
meaning; htmx 2 retains its named-event meaning during compatibility. The
implementation validates and HTML-escapes the ID before building the selector.
`Fragment.swap` is preserved; an omitted swap uses htmx's `innerHTML` default.

This changes the htmx 4 interpretation of `Fragment.target` from event name to
DOM target. The implementation therefore requires public-contract approval,
documentation, tests, and migration notes. htmx 2 retains its named-event
mapping during the compatibility window.

### 6. OOB-only and partial-only frames never clear the main target

htmx 4's SSE extension adds `swapEmpty:false` unless the application explicitly
overrides it. An unnamed message containing only `hx-swap-oob` elements or
`<hx-partial>` elements therefore leaves the connection target untouched.

Chirp relies on that behavior but still validates its own rendered update:

- a missing block raises `BlockNotFoundError` before a frame is sent;
- an empty rendered `Fragment` is a trust failure, not a no-op update;
- a raw `SSEEvent(data="")` remains a valid literal transport frame;
- clearing a main target requires an explicit application `swapEmpty:true`
  choice, not an accidental empty render.

Existing OOB markup remains valid inside an unnamed message:

```text
data: <div id="alerts" hx-swap-oob="beforeend">New alert</div>

```

### 7. Named events are DOM events only

Named events carry application notifications, lifecycle signals, and close
messages:

```text
event: notification
id: 42
data: {"title":"New message"}

```

On htmx 4 the source element receives `notification`; application JavaScript
may use `hx-on:notification` or `addEventListener`. Named events do not render
HTML, even if `data` happens to contain markup.

Chirp's framework control names must use a reserved `chirp:` prefix. A close
event remains named because it is lifecycle control, not rendered output.
Generator-level errors remain named diagnostic events and DevTools records.
A debug rendering error for a targeted `Fragment`, however, is delivered as an
unnamed targeted partial so the failed region remains visibly actionable.

### 8. Signals use one unnamed frame and CSS-selector partials

Signals keep one `/_chirp/live` connection. htmx 4 signal sinks receive a
stable marker in addition to their SSR seed:

```html
<span data-chirp-signal="balance">10</span>
<strong data-chirp-signal="balance">10</strong>
```

One emitted value becomes one unnamed message with a partial targeted by the
plain CSS attribute selector:

```html
<hx-partial hx-target='[data-chirp-signal="balance"]'>
  11
</hx-partial>
```

htmx 4 resolves partial targets with `document.querySelectorAll`, so the same
rendered value updates every matching sink. This preserves one producer, one
connection, and one message per topic without injecting layout wrappers or
requiring per-instance IDs. Signal names already pass a restricted validator;
the implementation must still escape them independently for HTML and CSS.

`signal()`, `signal_block()`, and `signal_bind()` continue to record topic
discovery and SSR values. The implementation task updates their emitted markup
for the selected client tier; it does not change application data flow.

### 9. Reconnect remains application-owned

htmx 4 tracks the last received `id:` and sends `Last-Event-ID` when it
reconnects. Background pause uses the same path. Chirp keeps RFC 007 unchanged:

- `SSEEvent(id=...)` advances the browser cursor;
- Chirp exposes `request.headers.get("last-event-id")`;
- the application validates the cursor and replays from its durable store;
- Chirp does not buffer, assign IDs, or promise replay.

`hx-sse:connect` defaults to reconnect with exponential backoff and pauses in a
background tab. Those are client behaviors, not reasons to add server state.

### 10. Cancellation and cleanup stay connection-scoped

Removing or replacing the source element cancels the fetch stream. Chirp's
disconnect monitor cancels the producer and closes the async generator so user
`finally` blocks run. Reconnect creates a new request and a new captured request
context; it never revives the prior generator or mutable context.

Authentication, session audience, CSRF context, CSP nonce, and `g` remain
pinned to one connection as documented today. Revocation takes effect on the
next connection unless the application explicitly terminates the current one.

## Wire examples

### Unnamed main update

```text
data: <p>Build complete</p>

```

The connection's normal target is swapped.

### Named DOM event

```text
event: deploy-finished
id: 108
data: production

```

No HTML swap occurs. The source element dispatches `deploy-finished`.

### OOB-only update

```text
data: <div id="nav-count" hx-swap-oob="innerHTML">4</div>

```

`#nav-count` updates and the connection target remains intact.

### Targeted partial

```text
data: <hx-partial hx-target="#stats"><dl>...</dl></hx-partial>

```

Only `#stats` updates.

### One signal, many sinks

```text
data: <hx-partial hx-target='[data-chirp-signal="balance"]'>11</hx-partial>

```

Every balance sink receives the same rendered value from one shared stream.

### Reconnect

```text
id: 108
data: <hx-partial hx-target="#feed" hx-swap="beforeend">...</hx-partial>

```

On reconnect the htmx 4 request includes `Last-Event-ID: 108`. The application
queries and emits only records after 108.

## Compatibility and rollout

1. #543 establishes htmx 2.0.10 as the verified rollback baseline.
2. #545 owns explicit htmx 4 beta/RC provisioning and tier metadata.
3. #546 normalizes htmx 4 request headers, including `HX-Request-Type`.
4. #553 implements the selected `EventStream` dialect and SSE markup.
5. #544 migrates signal sinks and fan-out to selector-targeted partials.
6. #547 adds tier-aware startup diagnostics.
7. #542 updates DevTools lifecycle events without duplicate records.
8. #551 may flip the default only after GA and the complete release gate.

During preview, htmx 2 and htmx 4 tests run as separate, explicit lanes. A
single response stream never attempts to satisfy both clients simultaneously.
Rollback disables preview provisioning and returns to the unchanged htmx 2.0.10
markup and named-fragment formatting.

Applications that manually consume `SSEEvent` through `EventSource` keep the
literal SSE wire. Applications that currently depend on named HTML events being
swapped must migrate to `Fragment(target=...)` or explicit unnamed
`<hx-partial>`/OOB markup before htmx 4 becomes their active tier.

## Security, cache, proxy, and CSP consequences

- SSE endpoints keep `Cache-Control: no-cache`, `X-Accel-Buffering: no`, and
  same-origin defaults. Intermediaries must not buffer the stream.
- htmx 4 uses fetch, so same-origin cookies and configured request headers are
  available. Cross-origin streams still require an explicit allowed origin and
  credential policy; no wildcard is introduced.
- `Last-Event-ID` remains untrusted input. Applications validate length,
  syntax, authorization scope, and retention bounds before querying.
- Partial targets are framework-generated from validated DOM IDs or validated
  signal markers. Raw application HTML retains normal htmx trust boundaries.
- CSP provisioning must load the exact version-matched htmx core and SSE
  extension in order, with current nonce/self-hosting policy. No loose beta
  range is acceptable.
- Heartbeats remain SSE comments. They do not enter the HTML swap pipeline.
- Named event data is application input to DOM event handlers. Chirp does not
  evaluate it or convert JSON into executable script.

## Free-threading consequences

The dialect is an immutable per-connection value. Rendering retains the
existing captured context boundary. Signal topic markers are produced from the
request-scoped referenced-topic set; no process-global sink registry or mutable
per-browser map is added. The shared signal bus keeps its existing lock and
lifecycle contracts.

Required concurrency proof includes simultaneous htmx 2 and htmx 4 streams,
two htmx 4 streams with different users/topic scopes, disconnect during render,
and reconnect after context teardown.

## Browser spike evidence

`tests/spikes/test_htmx4_sse_preview.py` is an opt-in, offline-at-runtime
Playwright spike. It reads assets from an exact upstream checkout and verifies:

- htmx core SHA-256
  `192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68`;
- SSE extension SHA-256
  `aa9aa14f10ddbf13a8fc4f8bbd6bc14e0b09b64d668d17e831e69763eac72558`;
- unnamed main HTML swaps;
- OOB-only and partial-only frames preserve the main target;
- one frame can update multiple explicit targets;
- one CSS-selector partial updates multiple signal sinks;
- named messages dispatch without swapping;
- an empty message does not clear the connection target;
- reconnect sends the last received event ID;
- two simultaneous SSE connections clean up independently.

Reproduce it with:

```bash
git clone --depth 1 --branch v4.0.0-beta5 \
  https://github.com/bigskysoftware/htmx.git /tmp/htmx-4.0.0-beta5
uv sync --no-sources --group dev --group browser
CHIRP_HTMX4_SSE_SPIKE=1 \
HTMX4_SOURCE_ROOT=/tmp/htmx-4.0.0-beta5 \
  uv run pytest tests/spikes/test_htmx4_sse_preview.py -q --tb=short
```

Result on 2026-07-06: `1 passed` with Chromium, htmx `4.0.0-beta5`, and the
pinned asset hashes above.

## Required implementation proof

- Unit tests for literal `SSEEvent`, unnamed `Fragment`, targeted `Fragment`,
  OOB-only, empty, close, retry, and render-error frames in each dialect.
- End-to-end `TestClient` tests for htmx 2, htmx 4, and generic SSE clients.
- `tests/contracts/` fixtures for mixed provisioning, legacy attributes under
  htmx 4, missing targets, missing blocks, and dead signal bindings.
- Testing-helper parity for connection markup, named DOM events, partial/OOB
  targets, event IDs, and heartbeats.
- Playwright coverage for initial connect, messages, reconnect, background
  pause/resume, disconnect, element removal, server error, malformed event,
  named close, OOB, partials, signals, and no-JS SSR seeds.
- Concurrency coverage for connection context, audiences, and topic isolation.
- DevTools evidence for attempts, status, message class, target, swap, event ID,
  reconnect, cancellation, and errors without payload leakage.
- Updated README, realtime production guide, SSE site guide, signal docs,
  examples, scaffolds, public API notes, migration notes, and changelog.

## Steward synthesis

The required stewards agree that the named-event collision must be resolved
before implementation. Because two or more independent stewards identify the
same failure, the repository convergence rule promotes it to P0 for synthesis:
**a named event cannot remain both a rendered swap channel and an application
DOM event on htmx 4.** The accepted resolution is the unnamed-HTML/partial
contract above.

The global sweep used for this accepted P0 was:

```bash
rg -n 'sse-swap|sse-connect|hx-ext="sse"|Fragment.*target|SSEEvent' \
  src tests docs examples site/content \
  -g '*.py' -g '*.md' -g '*.html'
```

### Raw steward signals

```text
Steward: Rendering
Area: Fragment-to-SSE envelope
Severity: P1
Invariant: Named blocks remain the only render source; transport wrappers must not create a parallel template path.
Evidence: src/chirp/templating/returns.py:115 -> src/chirp/realtime/sse.py:416
User Impact: Reusing named events for htmx 4 swaps would silently stop targeted rendered updates.
Required Fix: Render the existing Fragment block once, then add an unnamed hx-partial envelope for the htmx 4 dialect.
Required Proof: Missing-block, empty-render, target, swap, and parsed-DOM tests.
Collateral: Fragment/SSE docs, examples, migration notes, changelog.
Confidence: high
Verification Status:
machine-verified
```

```text
Steward: Realtime
Area: EventStream and SSEEvent semantics
Severity: P1
Invariant: EventStream remains post-load transport, literal SSEEvent fields survive, and reconnect state stays application-owned.
Evidence: src/chirp/realtime/events.py:13 -> docs/rfcs/007-sse-last-event-id-recovery.md:1
User Impact: Silent event-name rewriting would break EventSource consumers and make replay behavior ambiguous.
Required Fix: Keep named SSEEvent literal; classify rendered Fragment updates separately and preserve Last-Event-ID.
Required Proof: Wire parser, reconnect, cleanup, heartbeat, close, and generic-client tests.
Collateral: Realtime production guide and SSE reference.
Confidence: high
Verification Status:
machine-verified
```

```text
Steward: Protocol And Negotiation
Area: Request-aware SSE dialect selection
Severity: P1
Invariant: Typed return intent survives negotiation and one connection uses one immutable protocol contract.
Evidence: src/chirp/server/negotiation.py:703 -> src/chirp/realtime/sse.py:416
User Impact: Guessing from Accept alone can send htmx wrappers to generic clients or legacy frames to htmx 4.
Required Fix: Select the dialect from approved provisioning metadata plus request headers and carry it privately to the formatter.
Required Proof: htmx 2/4/raw matrix, sync/async parity, and simultaneous-connection tests.
Collateral: DevTools and request-header documentation.
Confidence: high
Verification Status:
machine-verified
```

```text
Steward: Contract Checks
Area: SSE and signal startup diagnostics
Severity: P1
Invariant: Detectable dead swaps and mixed client markup fail before deploy with actionable locations.
Evidence: src/chirp/contracts/rules_sse.py:365 -> src/chirp/contracts/rules_sse.py:429
User Impact: Current sse-swap cross-references would report false confidence on htmx 4.
Required Fix: Make checks tier-aware and diagnose legacy/new markup mismatch without changing severity silently.
Required Proof: End-to-end app.check fixtures for both tiers and mixed failures.
Collateral: Contract category docs; no severity change without separate approval.
Confidence: high
Verification Status:
machine-verified
```

```text
Steward: Testing Helpers
Area: SSE assertion parity
Severity: P1
Invariant: Public helpers exercise routing, negotiation, and the browser-visible message contract.
Evidence: src/chirp/testing/sse.py:33 -> src/chirp/testing/sse.py:118
User Impact: A helper that only understands sse-swap can pass while htmx 4 performs no swap.
Required Fix: Assert dialect, connection markup, named events, partial/OOB targets, and event IDs through real requests.
Required Proof: Helper regression tests plus Playwright DOM assertions.
Collateral: Testing guide and scaffolded tests where applicable.
Confidence: high
Verification Status:
machine-verified
```

```text
Steward: Narrative Docs
Area: Public SSE guidance
Severity: P2
Invariant: Docs distinguish shipped htmx 2 behavior from draft htmx 4 behavior and never invent configuration.
Evidence: site/content/docs/build-apps/streaming-updates/server-sent-events.md:89 -> src/chirp/config.py:231
User Impact: Copying current sse-swap guidance into an htmx 4 page yields a connection that receives events but never updates the DOM.
Required Fix: Publish migration guidance only with the implementation tier and keep this RFC marked draft until accepted.
Required Proof: Source/code link audit, site link checks, and example browser smoke.
Collateral: README, site SSE guide, examples, scaffolds, release notes.
Confidence: high
Verification Status:
machine-verified
```

No minority steward recommends a JSON side channel, client store, new return
type, or a second template system.

## Decision log

### Accepted in this draft

- Unnamed htmx 4 messages are the only automatic HTML swap messages.
- Named messages are DOM events only.
- Targeted rendered updates use post-render `<hx-partial>` envelopes.
- Signal fan-out uses one CSS-selector partial per topic and one shared stream.
- OOB/partial-only and empty messages preserve the main target by default.
- RFC 007 app-owned cursor recovery remains unchanged.
- htmx 2, htmx 4, and generic clients receive explicit dialects.
- Preview inputs are pinned to exact versions and verified asset hashes.

### Deferred to implementation issues

- The internal enum/type that carries the selected dialect.
- The exact approved htmx 4 provisioning surface (#545).
- Request header normalization and raw metadata exposure (#546).
- DevTools event names and payload schema (#542).
- Contract categories and any proposed severity change (#547).
- The htmx 2 support-window end date and GA default decision (#551).

### Rejected

- Mapping every named event to `HX-Trigger` or an HTML swap.
- Sending JSON state for the browser to render.
- Adding a second SSE-only template or component renderer.
- Treating `htmx-2-compat` as an SSE compatibility implementation.
- Guessing client dialect from `Accept` alone.
- Buffering events in Chirp for reconnect replay.
- Updating signal sinks with injected semantic-layout wrappers.
- Using loose beta/RC version ranges.

## Approval gate

Maintainer acceptance of this RFC authorizes only the contract described here.
Implementation still requires the repository's normal stop-and-ask checks for
public `Fragment` semantics, return-type documentation, signal markup/protocol,
contract severity, client provisioning, and any new public configuration.
