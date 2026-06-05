# RFC 007: SSE Last-Event-ID — App-Owned-Cursor Missed-Event Recovery

**Status:** Shipped behavior, boundary documented
**Author:** (proposal)
**Created:** 2026-06-05

**Decision:** Chirp only **reads** the `Last-Event-ID` request header and
**exposes** it to the SSE generator via `request.headers.get("last-event-id")`.
The framework **never** buffers or replays SSE events server-side. Missed-event
recovery is owned by the application: the app keeps its own cursor/store and
runs its own recovery query on reconnect.

**Proven by:** `tests/test_sse_integration.py:209-242`
(`TestSSEReconnectReplay`). Worked example:
`examples/standalone/sse_reconnect/`.

---

## 1. Problem Statement

The SSE protocol gives clients automatic reconnection. When a browser's
`EventSource` connection drops, the browser reconnects on its own and resends
the id of the last event it received in the `Last-Event-ID` request header. A
server that assigns ids to events can use that header to resume the stream
without gaps or duplicates.

The open question for a framework is: **who owns the buffer?** There are two
shapes:

1. **Framework-buffered replay.** The framework retains recently emitted events
   per stream (or per connection) and, on reconnect, replays everything after
   the client's `Last-Event-ID` automatically.
2. **App-owned-cursor recovery.** The framework reads `Last-Event-ID` and hands
   it to application code. The app decides what "missed" means and queries its
   own store to replay only the gap.

Chirp takes shape 2. This RFC states why, and where the bright line sits.

---

## 2. The Bright Line

> Chirp reads and exposes `Last-Event-ID`. It never buffers or replays events
> server-side.

Framework-buffered replay (shape 1) is **per-connection server state**, and
that is the line Chirp will not cross for SSE:

- **It is unbounded by default.** To replay "everything after id N" the
  framework must retain events until every possible reconnecting client has
  acknowledged them — which never happens for a client that simply went away.
  The buffer either grows without bound or silently drops events, turning a
  resumption guarantee into a lie.
- **It is per-stream state the framework cannot scope.** Only the app knows how
  many events to keep, how long a client may be gone before recovery is
  pointless, and whether an old event is even still meaningful (a "CPU high"
  alert may be stale; a chat message is not). A generic framework buffer cannot
  make those calls.
- **It does not survive the things that cause reconnects.** Reconnects happen
  precisely when a worker restarts, a deploy rolls, or a load balancer moves the
  client to a different process. An in-process framework buffer is gone exactly
  when it would be needed. Durable recovery requires a durable store — which is
  the app's database or stream, not framework memory.
- **It duplicates state the app already has.** The events worth replaying almost
  always already live in an application store (a table, an event log, a message
  bus). A framework buffer would be a second, weaker copy of that truth.

So the framework's responsibility ends at **transport**: read the header,
expose the value, assign nothing, retain nothing.

---

## 3. What Chirp Does (and Does Not) Do

### 3.1 Reads `Last-Event-ID`

On every (re)connect to an SSE route, the standard request headers include
`Last-Event-ID` when the browser sends it. Chirp exposes it through the normal
header API, with no special-casing:

```python
@app.route("/events", referenced=True)
def events(request):
    last_id = request.headers.get("last-event-id")  # str | None
    ...
```

A fresh connection (a new tab, a hard refresh) sends **no** `Last-Event-ID`;
`get(...)` returns `None`. The header value is an opaque, client-controlled
string, so the app validates/parses it (see §4).

### 3.2 Exposes the event `id` so the cursor advances

The reconnect cursor only travels on the SSE `id:` field. The browser updates
its "last event id" only when an event carries an `id`. In Chirp, `id` is a
field on `SSEEvent` (`src/chirp/realtime/events.py`):

```python
yield SSEEvent(data=html, event="deploy", id=str(event_id))
```

> **Note — `Fragment` events have no id.** When the generator yields a bare
> `Fragment`, Chirp renders it and emits `SSEEvent(data=html, event=target)`
> with **no** `id` (`src/chirp/realtime/sse.py`). A `Fragment` event therefore
> cannot advance the reconnect cursor. To make events resumable, render the
> fragment to HTML (`app.render(Fragment(...))`) and ship it inside an
> `SSEEvent` that also carries the `id`. The worked example does exactly this.

### 3.3 Does NOT buffer, assign ids, or replay

Chirp does not retain emitted events, does not assign ids, and does not replay
anything on reconnect. There is no framework-side ring buffer, no per-stream
history, no "replay since N" hook. The generator is re-invoked from scratch on
each connect, and what it yields is entirely the app's decision.

---

## 4. The App-Owned Recovery Pattern

The app owns three things the framework deliberately does not:

1. **The store** — an append-only log/table/stream of events, each with a
   monotonic id the app assigns.
2. **The cursor parse** — turning the opaque `Last-Event-ID` string into a
   position in that store (and deciding what a missing/garbage value means).
3. **The recovery query** — "give me only events after this cursor."

```python
@app.route("/events", referenced=True)
def events(request):
    last_id = request.headers.get("last-event-id")
    last_seen = int(last_id) if (last_id or "").isdigit() else 0  # app parses

    async def gen():
        for event in events_after(last_seen):       # app's recovery query
            yield SSEEvent(data=render(event), event="deploy", id=str(event.id))

    return EventStream(gen())
```

Behavior:

- **Fresh tab** (`Last-Event-ID` absent → cursor `0`): the app replays its full
  retained log.
- **Reconnect** (`Last-Event-ID: 2`): the app replays only events `3, 4, 5, …`.
  No duplicates, no full re-send.
- **Garbage/old cursor**: the app decides — start from the beginning, start from
  the oldest retained event, or reject. The framework has no opinion.

The verified test `tests/test_sse_integration.py:210` asserts exactly this:
two events seen on the first connection, only the missed pair replayed on
reconnect, and a full replay for a fresh tab.

---

## 5. Non-Goals

- **No framework event buffer.** Chirp will not retain emitted SSE events for
  replay. (This is the bright line of §2.)
- **No automatic id assignment.** The app assigns ids that mean something in its
  own store; the framework does not invent them.
- **No "replay since N" framework hook.** Recovery is an ordinary query in the
  generator, not a framework extension point.
- **No durability guarantees.** If an app wants recovery to survive worker
  restarts, its store must be durable. Chirp guarantees only that it will hand
  the generator the client's `Last-Event-ID`.
- **No change to `EventStream`/`SSEEvent` shape.** The existing types already
  carry everything needed (`id`, `event`, `data`).

---

## 6. Alternatives Considered

### 6.1 Framework-buffered replay (rejected)

A built-in per-stream ring buffer with automatic "replay after Last-Event-ID."
Rejected for the reasons in §2: unbounded/lossy by nature, un-scopable by a
generic framework, dead exactly when reconnects happen (worker/deploy churn),
and a duplicate of state the app already holds.

### 6.2 A `replay_since` callback on `EventStream` (rejected)

`EventStream(gen, replay_since=lambda last_id: ...)` would have formalized a
recovery seam. Rejected as redundant: the generator already receives the request
and can read `Last-Event-ID` itself, then branch. Adding a callback would split
one obvious place (the generator) into two and imply the framework owns part of
recovery, blurring the bright line.

---

## 7. Acceptance Criteria

- `request.headers.get("last-event-id")` returns the client's resent id on
  reconnect and `None` on a fresh connection.
- `SSEEvent(id=...)` is emitted on the wire as an `id:` line
  (`src/chirp/realtime/events.py` `SSEEvent.encode`).
- No symbol in `src/chirp` retains emitted SSE events for replay (no framework
  buffer).
- `tests/test_sse_integration.py:209-242` passes: fresh-connect full replay,
  reconnect gap-only replay.
- `examples/standalone/sse_reconnect/` runs and its tests pass, demonstrating
  the app-owned-cursor pattern end-to-end through the ASGI pipeline.
