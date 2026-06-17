# Optimistic Apply

The blessed, no-build optimistic-UI primitive. `optimistic_attrs([...ops])`
paints a mutation locally and instantly from the client's **own** pre-mutation
snapshot, lets htmx do the real request, swaps the authoritative server fragment
on success (last-write-wins), and reverts to the snapshot only when no
authoritative fragment lands.

**Zero per-client server view state** — the `/toggle-like` handler is identical
with or without the adapter, allocates nothing per client, and is never told an
optimistic apply happened. The rollback baseline lives in the browser. This is
the structural advantage over diff-push frameworks that keep per-client server
view state.

## Run

```bash
python app.py
```

Open <http://localhost:8000>. In DevTools → Network, throttle to "Slow 3G":

- **Like** — the heart and count update instantly, then the authoritative server
  fragment swaps in and confirms (`chirp:island:action` → `confirmed`).
- **Save** — shows "Saving…" instantly, then reverts when the 503 lands
  (`chirp:island:action` → `reverted`); no authoritative fragment, so the
  client's own snapshot is restored.

## The ~80% ceiling

`optimistic_apply` closes ~80% of the optimistic-UI gap with zero server state.
It is **one in-flight optimistic mutation per region**, **last-write-wins** via
the authoritative swap (no CRDT/OT merge), and requires a **replacing** swap
(`outerHTML`/`innerHTML`). For collaborative concurrent editing with
convergence, reach for a framework island instead.
