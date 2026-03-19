# Islands — No-Build Client-Managed Surfaces

Chirp's islands runtime lets you mount isolated client-owned widgets inside
server-rendered pages. This example uses `island_attrs()` and a plain ES module
— no bundler required.

## Run

```bash
PYTHONPATH=src python examples/standalone/islands/app.py
```

Open http://127.0.0.1:8000 and click the counter. Open the console to see
`chirp:island:mount` events.

## What It Demonstrates

- **AppConfig(islands=True)** — injects the islands bootstrap script
- **island_attrs()** — generates `data-island`, `data-island-props`, `data-island-src`
- **SSR fallback** — content inside the mount root works when JS is disabled
- **Dynamic adapter** — `counter.js` is loaded via `import()` when the island mounts
- **Lifecycle** — mount/unmount/remount on htmx swaps (navigate away and back to see remount)

## Files

- `app.py` — Chirp app with `islands=True`
- `templates/index.html` — page with `island_attrs("counter", ...)`
- `static/counter.js` — ES module adapter with `mount`/`unmount`

## Adapter Contract

The runtime calls `adapter.mount(payload, api)` when an island is discovered.
The adapter can return a cleanup function; it's called before htmx swaps.
`adapter.unmount(payload, api)` is optional.

Payload includes: `name`, `id`, `version`, `src`, `props`, `element`.
